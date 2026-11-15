"""Import a granted project roster, then let an administrator choose local roles.

Subjects arrive as patients. Other members arrive without a role. The same source
record is not imported twice. A later role change clears patient assignments;
an existing login binding stops matching until it is reviewed again.

T55 canonical 切换（cutover plan 波次 6）：域为 canonical 时，subject 不再写
users（legacy 的患者=账号同文档形态），改经 create_from_source 创建无账号
临床患者，并在同一事务写入导入台账（外部引用 + 审计原子提交）；member 仍
是账号，继续落 users。存量 legacy 行为逐字保留（fake Database 无状态文档
时 domain_mode 返回 legacy）。账号创建与患者-账号关联在 canonical 下是
分离的可选显式步骤，导入绝不推断账号。
"""
import hashlib
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import HTTPException
from pymongo import ASCENDING
from pymongo.errors import DuplicateKeyError

from app.core.patient_access import patient_assignment_field, patient_domain_mode
from app.db.transactions import run_transaction
from app.patients.repository import (PATIENTS, ClinicalPatientRepository,
                                     PatientDomainError, source_key)
from app.patients.schemas import SourcePatientIdentity

from .catalog_service import people as load_people

LOCAL_ROLES = {"unassigned", "patient", "doctor", "health_manager"}
ROLE_FOR_KIND = {"subject": "patient", "member": "unassigned"}
# canonical 导入台账：subject → 临床患者的导入审计与项目归属（clinical_patients
# 的 source 口径是全局源患者，不含项目维度，项目过滤以台账为准）。
IMPORT_LEDGER = "patient_source_imports"


def _storage_key(origin, person_key):
    return hashlib.sha256(f"{origin}\n{person_key}".encode()).hexdigest()


async def _ensure_index(users):
    await users.create_index([("source_person_key", ASCENDING)], unique=True,
                             name="unique_source_person",
                             partialFilterExpression={"source_person_key": {"$type": "string"}})


def _public(doc):
    return {"id": str(doc["_id"]), "name": doc.get("name") or "", "role": doc.get("role"),
            "source_kind": doc.get("source_kind"), "source_person_ref": doc.get("source_person_ref"),
            "source_project_id": doc.get("source_project_id"),
            "subject_code": doc.get("source_subject_code"),
            "practitioners": list(doc.get("practitioners") or []),
            "health_managers": list(doc.get("health_managers") or [])}


def _subject_public(clinical, row):
    """canonical subject 的对外形状：与 legacy _public 同键，id 为临床患者 ID。"""
    return {"id": clinical["patient_id"], "name": clinical.get("name") or "",
            "role": "patient", "source_kind": "subject",
            "source_person_ref": row.get("source_person_ref"),
            "source_project_id": row.get("source_project_id"),
            "subject_code": row.get("source_subject_code"),
            "practitioners": [str(item) for item in (clinical.get("practitioners") or [])],
            "health_managers": [str(item) for item in (clinical.get("health_managers") or [])]}


def _source_identity(origin, person):
    """RosterPerson → canonical 源患者身份（source_person_key 口径迁移到
    repository.source_key：origin + system + environment + source patient_id）。"""
    return SourcePatientIdentity.model_validate({
        "origin": origin, "system": person["source"]["system"],
        "environment": person["source"]["environment"],
        "patient_id": person["source_patient_id"]})


async def _import_canonical_subject(db, actor, project_id, origin, person, evidence_reference):
    """创建无账号临床患者，并与导入台账同事务原子提交。

    返回 True 表示新创建；False 表示该源患者已导入（source_key 唯一索引
    防重，冲突按已存在计数，绝不复激活）。canonical 实体创建本身 fail-closed
    （require_canonical + 索引前置校验），状态/索引未就绪时如实上抛。
    """
    identity = _source_identity(origin, person)
    key = source_key(identity)
    if await db[PATIENTS].find_one({"source_key": key}, {"_id": 1}):
        return False
    evidence_reference = evidence_reference or f"project-roster-import:{project_id}"

    async def write(session):
        document = await ClinicalPatientRepository(db).create_from_source(
            identity, reviewer=str(actor.id), evidence_reference=evidence_reference,
            name=person["display_name"] or person["person_key"], session=session)
        await db[IMPORT_LEDGER].insert_one({
            "_id": ObjectId(), "patient_id": document["patient_id"], "source_key": key,
            "source_origin": origin, "source_project_id": project_id,
            "source_kind": person["kind"], "source_person_ref": person["person_key"],
            "source_subject_id": person.get("subject_id"),
            "source_subject_code": person.get("subject_code"),
            "imported_by": str(actor.id), "evidence_reference": evidence_reference,
            "created_at": datetime.now(timezone.utc)}, session=session)
        return True

    try:
        return await run_transaction(db, write,
            error_code="PEOPLE_IMPORT_TRANSACTION_UNAVAILABLE",
            error_message="导入事务未能确认提交，请使用相同请求重试")
    except PatientDomainError as error:
        if error.code == "SOURCE_PATIENT_ALREADY_EXISTS":
            return False
        raise


async def list_imported_people(db, origin, project_id):
    # domain-dispatch: 迁移完成后可删
    if await patient_domain_mode(db) == "canonical":
        # canonical：member 仍在 users（账号域），subject 经台账取回临床患者。
        cursor = db.users.find({"source_origin": origin, "source_project_id": project_id})
        people = [_public(row) async for row in cursor]
        rows = await db[IMPORT_LEDGER].find(
            {"source_origin": origin, "source_project_id": project_id}).to_list(None)
        for row in rows:
            clinical = await db[PATIENTS].find_one({"patient_id": row["patient_id"]})
            if clinical:
                people.append(_subject_public(clinical, row))
        return sorted(people, key=lambda item: item.get("name") or "")
    cursor = db.users.find({"source_origin": origin, "source_project_id": project_id}).sort("name", 1)
    return [_public(row) async for row in cursor]


async def import_project_people(db, client, actor, project_id, *, evidence_reference=None):
    origin = client.source_origin
    # domain-dispatch: 迁移完成后可删
    canonical = await patient_domain_mode(db) == "canonical"
    if canonical:
        # 台账项目过滤索引：部署侧维护职责，幂等创建（与 users 幂等索引同风格）。
        await db[IMPORT_LEDGER].create_index(
            [("source_origin", ASCENDING), ("source_project_id", ASCENDING)],
            name="patient_import_project_scope")
    await _ensure_index(db.users)
    created = existing = 0
    cursor = None
    for _ in range(100):
        page = await load_people(client, project_id, limit=100, cursor=cursor)
        for person in page["data"]:
            if canonical and person["kind"] == "subject":
                if await _import_canonical_subject(db, actor, project_id, origin,
                                                   person, evidence_reference):
                    created += 1
                else:
                    existing += 1
                continue
            key = _storage_key(origin, person["person_key"])
            if await db.users.find_one({"source_person_key": key}, {"_id": 1}):
                existing += 1
                continue
            now = datetime.now(timezone.utc)
            role = ROLE_FOR_KIND[person["kind"]]
            document = {
                "_id": ObjectId(),
                "email": f"import-{key[:32]}@source-import.invalid",
                "name": person["display_name"] or person["person_key"],
                "password_hash": "!",
                "role": role,
                "permissions": [],
                "is_active": True,
                "created_at": now,
                "updated_at": now,
                "source_person_key": key,
                "source_origin": origin,
                "source_project_id": project_id,
                "source_kind": person["kind"],
                "source_person_ref": person["person_key"],
                "source_subject_id": person.get("subject_id"),
                "source_subject_code": person.get("subject_code"),
                "source_patient_id": person.get("source_patient_id"),
                "source_user_id": person.get("source_user_id"),
                "oidc_subject": person.get("oidc_subject"),
                "imported_by": str(actor.id),
                "practitioners": [],
                "health_managers": [],
                "patients": [],
                "role_reviews": [],
            }
            try:
                await db.users.insert_one(document)
            except DuplicateKeyError:
                existing += 1
            else:
                created += 1
        if not page["page"]["has_more"]:
            break
        cursor = page["page"]["next_cursor"]
    else:
        raise HTTPException(502, detail={"code": "SOURCE_ROSTER_TOO_LARGE"})
    return {"created": created, "existing": existing,
            "people": await list_imported_people(db, origin, project_id)}


async def assign_imported_role(db, actor, user_id, role, evidence_reference):
    if role not in LOCAL_ROLES:
        raise HTTPException(422, detail={"code": "INVALID_ROLE"})
    if not ObjectId.is_valid(user_id):
        raise HTTPException(422, detail={"code": "INVALID_USER_ID"})
    user = await db.users.find_one({"_id": ObjectId(user_id), "source_person_key": {"$type": "string"}})
    if not user:
        raise HTTPException(404, detail={"code": "IMPORTED_PERSON_NOT_FOUND"})
    if user.get("role") == role:
        return _public(user)
    uid = str(user["_id"])
    now = datetime.now(timezone.utc)
    review = {"role": role, "previous_role": user.get("role"), "actor_id": str(actor.id),
              "evidence_reference": evidence_reference, "at": now}
    # domain-dispatch: 迁移完成后可删
    if await patient_domain_mode(db) == "canonical":
        # 角色变更清空患者归属的不变量在 canonical 下同样成立：canonical 患者
        # 的医护关系在 clinical_patients，不清除会让已改岗成员继续可见。
        await db[PATIENTS].update_many(
            {"$or": [{"practitioners": uid}, {"health_managers": uid}]},
            {"$pull": {"practitioners": uid, "health_managers": uid}, "$set": {"updated_at": now}})
    await db.users.update_many(
        {"$or": [{"practitioners": uid}, {"health_managers": uid}]},
        {"$pull": {"practitioners": uid, "health_managers": uid}, "$set": {"updated_at": now}})
    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"role": role, "patients": [], "practitioners": [], "health_managers": [], "updated_at": now},
         "$push": {"role_reviews": review}})
    user.update(role=role, patients=[], practitioners=[], health_managers=[])
    return _public(user)


async def _imported_person(db, user_id):
    if not ObjectId.is_valid(user_id):
        raise HTTPException(422, detail={"code": "INVALID_USER_ID"})
    user = await db.users.find_one({"_id": ObjectId(user_id), "source_person_key": {"$type": "string"}})
    if not user:
        raise HTTPException(404, detail={"code": "IMPORTED_PERSON_NOT_FOUND"})
    return user


async def _imported_subject(db, patient_id):
    """canonical subject 定位：导入台账 + clinical_patients（active）。"""
    row = await db[IMPORT_LEDGER].find_one(
        {"patient_id": str(patient_id), "source_kind": "subject"})
    clinical = await db[PATIENTS].find_one({"patient_id": str(patient_id)})
    if (not row or not clinical or clinical.get("status") != "active"):
        raise HTTPException(404, detail={"code": "IMPORTED_PERSON_NOT_FOUND"})
    return clinical, row


async def set_imported_care(db, actor, patient_id, practitioner_id, *, assigned, evidence_reference):
    """Connect a doctor or health manager to a patient imported from the same project."""
    if patient_id == practitioner_id:
        raise HTTPException(422, detail={"code": "CARE_SELF_ASSIGNMENT"})
    # domain-dispatch: 迁移完成后可删
    if await patient_domain_mode(db) == "canonical":
        clinical, import_row = await _imported_subject(db, patient_id)
    else:
        clinical = await _imported_person(db, patient_id)
        import_row = None
    practitioner = await _imported_person(db, practitioner_id)
    # 项目归属核对：legacy 在患者文档上，canonical 在导入台账上（临床患者
    # 的 source 口径是全局源患者，无项目维度）。
    patient_project = import_row or clinical
    if (patient_project.get("source_origin") != practitioner.get("source_origin")
            or patient_project.get("source_project_id") != practitioner.get("source_project_id")):
        raise HTTPException(409, detail={"code": "DIFFERENT_PROJECT"})
    if (import_row is None and clinical.get("role") != "patient") or (
            import_row is not None and import_row.get("source_kind") != "subject"):
        raise HTTPException(409, detail={"code": "CARE_ROLE_MISMATCH"})
    if practitioner.get("role") not in {"doctor", "health_manager"}:
        raise HTTPException(409, detail={"code": "CARE_ROLE_MISMATCH"})
    # 角色输入域已由上方守卫限定为 {"doctor", "health_manager"}，
    # patient_assignment_field 的未知角色抛错收紧在此不可达，行为逐字等价
    # （redundancy review 批次 1）
    field = patient_assignment_field(practitioner["role"])
    patient_links = list(clinical.get(field) or [])
    clinician_links = list(practitioner.get("patients") or [])
    practitioner_ref, patient_ref = str(practitioner["_id"]), (
        clinical["patient_id"] if import_row is not None else str(clinical["_id"]))
    if assigned:
        if practitioner_ref not in patient_links:
            patient_links.append(practitioner_ref)
        if patient_ref not in clinician_links:
            clinician_links.append(patient_ref)
    else:
        patient_links = [item for item in patient_links if item != practitioner_ref]
        clinician_links = [item for item in clinician_links if item != patient_ref]
    now = datetime.now(timezone.utc)
    review = {"action": "assign" if assigned else "remove", "field": field,
              "practitioner_id": practitioner_ref, "actor_id": str(actor.id),
              "evidence_reference": evidence_reference, "at": now}
    if import_row is not None:
        # canonical：医护关系写 clinical_patients。care_reviews 是临床文档上的
        # 处置审计数组（与 legacy users 文档同风格），不进入 patient_response 投影。
        await db[PATIENTS].update_one({"patient_id": clinical["patient_id"]},
                                      {"$set": {field: patient_links, "updated_at": now},
                                       "$push": {"care_reviews": review}})
    else:
        await db.users.update_one({"_id": clinical["_id"]},
                                  {"$set": {field: patient_links, "updated_at": now}, "$push": {"care_reviews": review}})
    await db.users.update_one({"_id": practitioner["_id"]},
                              {"$set": {"patients": clinician_links, "updated_at": now}})
    clinical[field] = patient_links
    return _subject_public(clinical, import_row) if import_row is not None else _public(clinical)
