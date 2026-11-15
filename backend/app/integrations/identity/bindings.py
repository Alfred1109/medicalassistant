"""Privileged maintenance operation after human account verification, never by name."""
from datetime import datetime
import secrets
from urllib.parse import urlsplit

from bson import ObjectId

from app.core.reviewed_link import audit_entry, disable_link, insert_link, validate_review

from .service import digest


async def manage_binding(db, *, issuer, subject, actor_id, reviewer, evidence_reference,
                         action="bind", apply=False, approved_role=None):
    parsed = urlsplit(issuer)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or issuer.endswith("/")):
        raise ValueError("Exact HTTPS issuer required")
    if not isinstance(subject, str) or not 1 <= len(subject) <= 255:
        raise ValueError("Verified source subject required")
    if not isinstance(actor_id, str) or not ObjectId.is_valid(actor_id):
        raise ValueError("Existing local actor ID required")
    if action not in {"bind", "disable", "review-role"}:
        raise ValueError("Unsupported binding operation")
    reviewer, evidence_reference = validate_review(
        reviewer, evidence_reference,
        missing_error=lambda: ValueError("Human reviewer and verification evidence reference required"),
        invalid_error=lambda: ValueError("Review reference is too long"),
        max_reviewer=255, max_evidence=1024)
    actor = await db.users.find_one({"_id": ObjectId(actor_id), **({"is_active": True} if action != "disable" else {})})
    if actor is None:
        raise ValueError("Existing active local actor required")
    if actor.get("role") not in {"admin", "doctor", "health_manager", "patient"}:
        raise ValueError("Existing role must be explicitly supported and reviewed")
    if action != "disable" and approved_role != actor["role"]:
        raise ValueError("Explicitly reviewed role must match the current local role")
    key = digest(issuer + "\0" + subject)
    existing = await db.oidc_principal_bindings.find_one({"_id": key})
    if action == "bind" and existing is not None:
        raise ValueError("Subject already has a binding record; cannot overwrite or revive")
    if action == "bind" and await db.oidc_principal_bindings.find_one({"issuer": issuer, "actor_id": actor_id}):
        raise ValueError("Local actor already has a subject binding in this issuer")
    if action in {"disable", "review-role"} and (not existing or existing.get("actor_id") != actor_id or not existing.get("enabled")):
        raise ValueError("Exact active binding required")
    result = dict(action=action, issuer=issuer, subject=subject, actor_id=actor_id,
                  approved_role=actor["role"], apply=apply, changes_local_role=False)
    if not apply:
        return result
    now = datetime.utcnow()
    revision = secrets.token_hex(32)
    audit = audit_entry(
        action=action, reviewer=reviewer, evidence_reference=evidence_reference, at=now,
        extra={"approved_role": actor["role"], "authorization_revision": revision})
    if action == "bind":
        # _id 与 issuer_actor_unique 收口并发；预检仍区分两条冲突文案。
        await insert_link(
            db.oidc_principal_bindings,
            dict(
                _id=key, issuer=issuer, subject=subject, actor_id=actor_id, enabled=True,
                verified_by=reviewer, verified_at=now,
                approved_role=actor["role"],
                authorization_revision=revision,
                evidence_reference=evidence_reference, audit=[audit]),
            conflict_queries=[{"_id": key}, {"issuer": issuer, "actor_id": actor_id}],
            conflict_error=lambda: ValueError(
                "Subject already has a binding record; cannot overwrite or revive"))
    elif action == "disable":
        await disable_link(
            db.oidc_principal_bindings,
            selector={"_id": key},
            active_filter={
                "issuer": issuer, "subject": subject, "actor_id": actor_id, "enabled": True,
                "authorization_revision": existing.get("authorization_revision")},
            set_fields={"enabled": False, "disabled_at": now, "authorization_revision": revision},
            audit_entry=audit,
            conflict_error=lambda: ValueError("Binding changed concurrently; no operation applied"))
    else:
        # review-role 改的是已批准角色，不是停用，不能走 disable 三态。
        updated = await db.oidc_principal_bindings.update_one(
            {"_id": key, "issuer": issuer, "subject": subject, "actor_id": actor_id,
             "enabled": True, "approved_role": existing.get("approved_role"),
             "authorization_revision": existing.get("authorization_revision")},
            {"$set": {"approved_role": actor["role"], "verified_by": reviewer,
                      "verified_at": now, "evidence_reference": evidence_reference,
                      "authorization_revision": revision}, "$push": {"audit": audit}})
        if updated.modified_count != 1:
            raise ValueError("Binding changed concurrently; no operation applied")
    return result
