"""Privileged maintenance operation after human account verification, never by name."""
from datetime import datetime
from urllib.parse import urlsplit

from bson import ObjectId

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
    if not reviewer.strip() or not evidence_reference.strip():
        raise ValueError("Human reviewer and verification evidence reference required")
    if len(reviewer) > 255 or len(evidence_reference) > 1024:
        raise ValueError("Review reference is too long")
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
    audit = dict(action=action, reviewer=reviewer.strip(), evidence_reference=evidence_reference.strip(), at=now,
                 approved_role=actor["role"])
    if action == "bind":
        # Atomic one-document state+audit. _id and issuer_actor_unique enforce races.
        await db.oidc_principal_bindings.insert_one(dict(
            _id=key, issuer=issuer, subject=subject, actor_id=actor_id, enabled=True,
            verified_by=reviewer.strip(), verified_at=now,
            approved_role=actor["role"],
            evidence_reference=evidence_reference.strip(), audit=[audit]))
    elif action == "disable":
        updated = await db.oidc_principal_bindings.update_one(
            {"_id": key, "issuer": issuer, "subject": subject, "actor_id": actor_id, "enabled": True},
            {"$set": {"enabled": False, "disabled_at": now}, "$push": {"audit": audit}})
        if updated.modified_count != 1:
            raise ValueError("Binding changed concurrently; no operation applied")
    else:
        updated = await db.oidc_principal_bindings.update_one(
            {"_id": key, "issuer": issuer, "subject": subject, "actor_id": actor_id,
             "enabled": True, "approved_role": existing.get("approved_role")},
            {"$set": {"approved_role": actor["role"], "verified_by": reviewer.strip(),
                      "verified_at": now, "evidence_reference": evidence_reference.strip()}, "$push": {"audit": audit}})
        if updated.modified_count != 1:
            raise ValueError("Binding changed concurrently; no operation applied")
    return result
