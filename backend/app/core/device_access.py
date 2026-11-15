"""Patient ownership and clinical management policy for device resources."""
from bson import ObjectId
from fastapi import HTTPException

from app.core.fences import AccountFenceStore, PatientFenceStore, dual_bump
from app.core.patient_access import (
    assigned_scope_ids, ensure_patient_access, load_patient_doc, patient_domain_mode,
    resolve_self_patient_entity,
)
from app.core.patient_identity import identity_key, load_identity_groups

# 设备域栅栏名（T67 缺陷 1 域化命名）：canonical 双载体落 account_fences 的
# ("device") 计数与 clinical_patients 的 _fence_device 字段。设备域不再与
# 康复/质控等域共用泛化名，避免同账号/同患者文档的跨域计数互相污染 CAS 复核。
DEVICE_ACCESS_FENCE = "device"


async def resolve_device_patient(db, actor, patient_id=None, *, session=None, fence=False):
    """A patient selects self; medical staff must select an assigned patient.

    患者角色的实体解析走内核域分派（resolve_self_patient_entity）：canonical
    经 resolve_self 的 verified 链接解析临床患者实体（显式绑定下账号 ID≠患者
    ID 不再前置即拒），legacy 保持同文档语义逐字不变。
    """
    if actor.role == "patient":
        target = await resolve_self_patient_entity(db, actor, patient_id, session=session)
        patient = await load_patient_doc(db, target, session=session)
    elif actor.role in {"doctor", "health_manager", "admin"}:
        if not isinstance(patient_id, (str, ObjectId)) or not str(patient_id):
            raise HTTPException(422, detail="请明确选择设备所属患者")
        target = str(patient_id)
        patient = (await load_patient_doc(db, target, session=session) if actor.role == "admin" else
                   await ensure_patient_access(db, target, str(actor.id), actor.role, session=session))
    else:
        raise HTTPException(403, detail="无权管理患者设备")
    if patient.get("is_active", True) is not True:
        raise HTTPException(404, detail="患者不存在或不可用")
    if fence:
        groups = await load_identity_groups(db, [actor.id], session=session)
        accounts = groups.get(identity_key(actor.id), [])
        account = accounts[0] if len(accounts) == 1 else None
        if (not account or account.get("role") != actor.role
                or account.get("is_active", True) is not True):
            raise HTTPException(403, detail="当前账号不可用")
        if await patient_domain_mode(db, session=session) == "canonical":
            # canonical 双载体栅栏（波次 5，cutover plan §3.2/3.3）：账号态 →
            # account_fences("device") 独立集合计数；患者归属态 →
            # clinical_patients._fence_device 字段。users 文档不再承担栅栏计数
            # （canonical 只读约定），无账号临床患者的绑定/手工读数由此解除
            # 「写阻」（T55 演练步骤 5 缺口闭合）。迁移窗口约束沿用
            # （fences.py §为什么栅栏计数不迁移）：切换时存量计数不迁移，
            # 双载体从空白起算，旧载体（users._device_access_fence）在切换
            # 窗口内停止递增。两跳在同一事务内整体提交/回滚（session 透传），
            # 账号授权复核仍在上方的 users 读取（账号域不变）。
            await dual_bump(
                (AccountFenceStore(db), str(account["_id"]), DEVICE_ACCESS_FENCE),
                (PatientFenceStore(db), str(patient["patient_id"]), DEVICE_ACCESS_FENCE),
                session=session)
        else:
            # legacy 载体逐字不变：账号与患者实体同文档（患者本人两次 $inc
            # 去重为一次），一次 $inc 同时覆盖"账号态"与"患者归属"两种语义。
            for document in {document["_id"]: document for document in (account, patient)}.values():
                value = document.get("_device_access_fence", 0)
                if type(value) is not int or value < 0:
                    raise HTTPException(503, detail="设备授权并发状态无效")
                result = await db.users.update_one({"_id": document["_id"]},
                    {"$inc": {"_device_access_fence": 1}}, session=session)
                if result.matched_count != 1:
                    raise HTTPException(403, detail="设备授权已变化")
    return str(patient["_id"])


async def ensure_device_access(db, device, actor, roles, *, write=False, session=None, fence=False):
    """Historical non-patient bindings remain visible only to administrators."""
    if write and device.get("status") == "deleted":
        raise HTTPException(409, detail="设备已解绑，不能继续修改")
    if actor.role == "admin" and not write:
        return
    if actor.role != "patient" and actor.role not in roles:
        raise HTTPException(403, detail="无权访问此设备")
    patient_id = device.get("patient_id")
    if not isinstance(patient_id, (str, ObjectId)) or not str(patient_id):
        raise HTTPException(404, detail="设备所属患者不可用")
    await resolve_device_patient(db, actor, patient_id, session=session, fence=fence)


async def device_patient_scope(db, actor, patient_id=None):
    """Return patient IDs; None is the administrator's read-only inventory.

    legacy：沿用 assigned_ids + is_active 过滤的原语义（extra_query 叠加于
    legacy 分支）。canonical：由内核 assigned_scope_ids 执行于
    clinical_patients，status=active 已内建等价的可用性收窄，is_active
    这类 legacy 专属条件不再叠加。
    """
    if patient_id is not None or actor.role == "patient":
        return [await resolve_device_patient(db, actor, patient_id)]
    if actor.role == "admin":
        return None
    if actor.role not in {"doctor", "health_manager"}:
        raise HTTPException(403, detail="无权查看患者设备")
    return await assigned_scope_ids(db, str(actor.id), actor.role, extra_query={
        "$or": [{"is_active": True}, {"is_active": {"$exists": False}}]})
