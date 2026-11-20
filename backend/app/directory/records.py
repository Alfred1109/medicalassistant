"""Persistent records for menus that previously had no stored result."""
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from app.core.patient_access import patient_domain_context
from app.core.fences import PatientFenceStore, legacy_document_fence
from app.db.transactions import run_transaction

# 标签业务唯一键 (name, category) 的唯一索引名。索引不进应用启动路径
# （app/db/indexes.py 不登记）：须先经 scripts/label_uniqueness_audit.py
# 盘点清零历史重复，再在维护窗口手工建索引，实施顺序见
# docs/tag-uniqueness-plan.md。索引缺位时本模块行为与历史一致
# （先查重友好拒绝），建索引后由 11000 兜底查重-插入竞态。
TAG_UNIQUE_INDEX_NAME = "uniq_tag_name_category"


def _now():
    return datetime.now(timezone.utc)


def _id(value):
    if not ObjectId.is_valid(str(value)):
        raise HTTPException(422, detail={"code": "INVALID_ID"})
    return ObjectId(str(value))


async def list_tags(db, category=None):
    query = {"category": category} if category else {}
    return [_tag(row) async for row in db.tags.find(query)]


def _tag(row):
    return {"id": str(row["_id"]), "name": row["name"], "category": row["category"], "color": row.get("color") or ""}


async def create_tag(db, name, category, color):
    name, category = name.strip(), category.strip()
    if not name or not category or len(name) > 40 or len(category) > 40:
        raise HTTPException(422, detail={"code": "INVALID_TAG"})
    if await db.tags.find_one({"name": name, "category": category}):
        raise HTTPException(409, detail={"code": "TAG_EXISTS"})
    document = {"_id": ObjectId(), "name": name, "category": category, "color": (color or "")[:20], "created_at": _now()}
    try:
        await db.tags.insert_one(document)
    except DuplicateKeyError:
        # 唯一索引（TAG_UNIQUE_INDEX_NAME）兜底查重-插入竞态：并发重复
        # 一律转换为既有 TAG_EXISTS 语义（409），错误码与响应不变。
        raise HTTPException(409, detail={"code": "TAG_EXISTS"}) from None
    return _tag(document)


async def delete_tag(db, tag_id):
    result = await db.tags.delete_one({"_id": _id(tag_id)})
    if result.deleted_count != 1:
        raise HTTPException(404, detail={"code": "TAG_NOT_FOUND"})
    return {"id": tag_id, "deleted": True}


async def set_account_active(db, user_id, active):
    updated = await db.users.update_one(
        {"_id": _id(user_id), "role": {"$in": ["doctor", "patient", "health_manager"]}},
        {"$set": {"is_active": active, "updated_at": _now()}})
    if updated.matched_count != 1:
        raise HTTPException(404, detail={"code": "ACCOUNT_NOT_FOUND"})
    return {"id": user_id, "is_active": active}


async def set_organization_active(db, organization_id, active):
    updated = await db.organizations.update_one(
        {"_id": _id(organization_id)}, {"$set": {"active": active, "updated_at": _now()}})
    if updated.matched_count != 1:
        raise HTTPException(404, detail={"code": "ORGANIZATION_NOT_FOUND"})
    return {"id": organization_id, "active": active}


async def registration_open(db):
    row = await db.system_settings.find_one({"_id": "system"})
    if not row or "allow_registration" not in row:
        return True
    return bool(row["allow_registration"])


async def save_system_setting(db, allow_registration):
    await db.system_settings.update_one(
        {"_id": "system"}, {"$set": {"allow_registration": allow_registration, "updated_at": _now()}}, upsert=True)
    return {"allow_registration": allow_registration}


async def read_preferences(db, user_id):
    row = await db.user_preferences.find_one({"_id": str(user_id)}) or {}
    return {"ui": row.get("ui") or {}, "notifications": row.get("notifications") or {}}


async def save_preferences(db, user_id, *, ui=None, notifications=None):
    changes = {"updated_at": _now()}
    if ui is not None:
        changes["ui"] = ui
    if notifications is not None:
        changes["notifications"] = notifications
    await db.user_preferences.update_one({"_id": str(user_id)}, {"$set": changes}, upsert=True)
    return await read_preferences(db, user_id)


def _template(row):
    return {"id": str(row["_id"]), "title": row["title"], "body": row["body"], "active": row.get("active", True)}


def _document(row):
    return {"id": str(row["_id"]), "patient_id": row["patient_id"], "patient_name": row.get("patient_name") or "",
            "title": row["title"], "body": row["body"], "status": row["status"],
            "signed_name": row.get("signed_name") or "", "signed_at": row.get("signed_at"),
            "created_by": row.get("created_by") or ""}


async def create_template(db, actor, title, body):
    title, body = title.strip(), body.strip()
    if actor.role not in {"admin", "doctor"} or not title or not body or len(title) > 120 or len(body) > 20000:
        raise HTTPException(422, detail={"code": "INVALID_TEMPLATE"})
    document = {"_id": ObjectId(), "title": title, "body": body, "active": True,
                "author_id": str(actor.id), "created_at": _now()}
    await db.consent_templates.insert_one(document)
    return _template(document)


async def list_templates(db):
    return [_template(row) async for row in db.consent_templates.find({"active": True})]


async def issue_consent(db, actor, template_id, patient_id):
    context = await patient_domain_context(db)
    if actor.role == "doctor":
        patient = await context.ensure_patient_access(patient_id, str(actor.id), "doctor")
    elif actor.role == "admin":
        patient = await context.load_patient_doc(patient_id)
    else:
        raise HTTPException(403, detail={"code": "ROLE_NOT_ALLOWED"})
    template = await db.consent_templates.find_one({"_id": _id(template_id), "active": True})
    if not template:
        raise HTTPException(404, detail={"code": "TEMPLATE_NOT_FOUND"})
    document = {"_id": ObjectId(), "template_id": str(template["_id"]),
                "patient_id": context.entity_id(patient),
                "patient_name": patient.get("name") or "", "title": template["title"], "body": template["body"],
                "status": "pending", "created_by": str(actor.id), "created_at": _now()}
    await db.consent_documents.insert_one(document)
    return _document(document)


async def _consent_scope(db, actor, patient_id):
    if actor.role == "patient":
        context = await patient_domain_context(db)
        resolved_patient_id = await context.ensure_self_patient_access(actor, patient_id)
        query = {"patient_id": resolved_patient_id}
    elif actor.role == "admin":
        query = {"patient_id": patient_id} if patient_id else {}
    elif actor.role == "doctor":
        if patient_id:
            context = await patient_domain_context(db)
            await context.ensure_patient_access(patient_id, str(actor.id), "doctor")
            query = {"patient_id": str(patient_id)}
        else:
            query = {"created_by": str(actor.id)}
    else:
        raise HTTPException(403, detail={"code": "ROLE_NOT_ALLOWED"})
    return query


async def list_consents(db, actor, patient_id=None):
    query = await _consent_scope(db, actor, patient_id)
    return [_document(row) async for row in db.consent_documents.find(query)]


async def list_pending_consent_summaries(db, actor):
    query = await _consent_scope(db, actor, None)
    return [
        {"id": str(row["_id"]), "title": row.get("title"), "created_at": row.get("created_at")}
        async for row in db.consent_documents.find(
            {**query, "status": "pending"}, {"title": 1, "created_at": 1})
    ]


async def read_consent(db, actor, document_id):
    row = await db.consent_documents.find_one({"_id": _id(document_id)})
    if not row:
        raise HTTPException(404, detail={"code": "CONSENT_NOT_FOUND"})
    if actor.role == "patient":
        context = await patient_domain_context(db)
        await context.ensure_self_patient_access(actor, row["patient_id"])
    if actor.role == "doctor" and row.get("created_by") != str(actor.id):
        context = await patient_domain_context(db)
        await context.ensure_patient_access(row["patient_id"], str(actor.id), "doctor")
    if actor.role not in {"patient", "doctor", "admin"}:
        raise HTTPException(403, detail={"code": "ROLE_NOT_ALLOWED"})
    return row


async def sign_consent(db, actor, document_id, signed_name, accepted):
    if actor.role != "patient":
        raise HTTPException(403, detail={"code": "PATIENT_SIGNATURE_ONLY"})
    signed_name = signed_name.strip()
    if accepted and not signed_name:
        raise HTTPException(422, detail={"code": "SIGNATURE_NAME_REQUIRED"})
    status = "signed" if accepted else "declined"

    async def apply(session):
        consent = await db.consent_documents.find_one({"_id": _id(document_id)}, session=session)
        if consent is None:
            raise HTTPException(404, detail={"code": "CONSENT_NOT_FOUND"})
        context = await patient_domain_context(db, session=session)
        await context.ensure_self_patient_access(actor, consent["patient_id"])
        if consent.get("status") != "pending":
            raise HTTPException(409, detail={"code": "CONSENT_CONCURRENT_UPDATE",
                                             "current_status": consent.get("status")})

        # Revalidate and serialize the authorization carrier in the same
        # transaction as the consent transition. Canonical link revocation is
        # an atomic verified -> disabled update on this exact document; touching
        # it here makes concurrent revocation conflict with this transaction.
        if context.is_canonical:
            account_id = str(actor.id)
            account = await db.users.find_one({"_id": _id(account_id)}, session=session)
            if not account or account.get("role") != "patient" or account.get("is_active", True) is not True:
                raise HTTPException(403, detail={"code": "PATIENT_NOT_ASSIGNED"})
            await legacy_document_fence(
                db.users, account, "_access_fence", session=session,
                error_code="CONSENT_ACCOUNT_FENCE_INVALID",
                error_message="患者账号并发状态异常")
            link = await db.patient_account_links.find_one({
                "account_id": account_id, "patient_id": consent["patient_id"],
                "status": "verified",
            }, session=session)
            if not link:
                raise HTTPException(403, detail={"code": "PATIENT_NOT_ASSIGNED"})
            link_update = await db.patient_account_links.update_one(
                {"_id": link["_id"], "account_id": account_id,
                 "patient_id": consent["patient_id"], "status": "verified"},
                {"$inc": {"_consent_access_fence": 1}}, session=session)
            if link_update.matched_count != 1:
                raise HTTPException(409, detail={"code": "CONSENT_AUTHORIZATION_CHANGED"})
            await PatientFenceStore(db).bump(
                consent["patient_id"], "consent", session=session,
                extra_query={"status": "active"})
        else:
            patient = await context.load_patient_doc(consent["patient_id"])
            await legacy_document_fence(
                db.users, patient, "_access_fence", session=session,
                error_code="CONSENT_ACCOUNT_FENCE_INVALID",
                error_message="患者账号并发状态异常")

        signed_at = _now()
        result = await db.consent_documents.update_one(
            {"_id": consent["_id"], "status": "pending"},
            {"$set": {"status": status, "signed_name": signed_name, "signed_at": signed_at}},
            session=session)
        if result.matched_count != 1:
            current = await db.consent_documents.find_one({"_id": consent["_id"]}, session=session)
            raise HTTPException(409, detail={"code": "CONSENT_CONCURRENT_UPDATE",
                                             "current_status": current.get("status") if current else None})
        current = await db.consent_documents.find_one({"_id": consent["_id"]}, session=session)
        if current is None:
            raise HTTPException(404, detail={"code": "CONSENT_NOT_FOUND"})
        return _document(current)

    return await run_transaction(db, apply,
        error_code="CONSENT_TRANSACTION_UNAVAILABLE",
        error_message="知情同意状态未能确认，请重新读取后再试；数据库必须支持事务")
