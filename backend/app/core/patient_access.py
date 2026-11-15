"""患者对象授权内核；不依赖认证组装或业务服务。

域模式分派：读取 patients/repository.py 的 patient_domain_state 单例
（clinical-patients-v1）。无状态文档时按现状默认走 legacy（users）路径；
显式 `{mode: "legacy"}`（回拨 SOP 载体）与无文档 legacy 行为完全一致，
走同一条 legacy 分支；canonical 模式走 ClinicalPatientRepository +
patient_account_links。模式读取失败或观察到未知状态一律 fail-closed
（拒绝请求），绝不静默回退 legacy。

分支标签（两类不要混删）：`mode == "canonical"` 是域分派分支，legacy
停用之后可以删；`legacy_user_id`、`submission_history`、无版本节点这类是
存量数据形态，不随域切换删除。

请求内单次读取（Wave 2 任务 B）：patient_domain_context(db, session=...) 返回
一个绑定好的访问器——域模式只读取一次，同一请求内的患者读取/归属校验/本人
解析全部复用这一结论，域分派细节不再散落到各服务层。事务内必须把 session
透传进来（否则状态读取会脱离事务快照）；只读展示路径用
patient_domain_context_safe（fail-safe unknown 口径，与 fail-closed 刻意分化）。
"""
from typing import Any, Dict, Optional

from bson import ObjectId
from fastapi import status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import PyMongoError

from app.core.exceptions import AppBaseException
from app.patients.legacy import LegacyPatientRepository, self_patient_id
from app.patients.repository import (
    ACCOUNT_LINKS, ClinicalPatientRepository, PatientDomainError,
    assigned_query as canonical_assigned_query, domain_mode as read_domain_mode)


class PatientAccessError(AppBaseException):
    """患者归属校验失败（对象级授权）。"""

    def __init__(self, message: str, error_code: str = "PATIENT_NOT_ASSIGNED",
                 status_code: int = status.HTTP_403_FORBIDDEN,
                 details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, status_code=status_code,
                         error_code=error_code, details=details)


def _domain_state_unavailable(reason: str) -> PatientAccessError:
    return PatientAccessError("患者域状态不可用，已拒绝访问",
                              error_code="PATIENT_DOMAIN_STATE_UNAVAILABLE",
                              status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                              details={"reason": reason})


async def patient_domain_mode(db, *, session=None) -> str:
    """读取域开关；`legacy`（无状态文档或显式 legacy 载体）与 `canonical`
    是合法观察结果，显式 legacy 与无文档 legacy 行为完全一致。"""
    try:
        return await read_domain_mode(db, session=session)
    except PatientDomainError as error:
        raise _domain_state_unavailable(error.code) from None
    except PyMongoError as error:
        raise _domain_state_unavailable("PATIENT_DOMAIN_STATE_READ_FAILED") from error


def is_domain_state_unavailable(error: PatientAccessError) -> bool:
    """消费方 catch-all 降级前的分流判据：canonical 二次状态读取异常
    （域状态不可用 503）必须透传，绝不能与归属失败（403）混同。"""
    return error.error_code == "PATIENT_DOMAIN_STATE_UNAVAILABLE"


async def patient_domain_mode_safe(db, *, fallback: str = "unknown") -> str:
    """观察域开关的 fail-safe 口径（统计聚合/只读导出等展示类路径专用）。

    读取失败或观察到不可用状态时返回 fallback（默认 "unknown"），绝不猜测
    域回退。与 patient_domain_mode 的 fail-closed（503 拒绝请求）刻意分化：
    只读展示路径域状态不可用不应 500 阻断页面，但 unknown ≠ legacy——消费方
    收到 unknown 必须把患者类指标降级为不可用并如实标记，不得按 legacy 聚合
    （canonical 患者会漏算、legacy 停用患者会误算）。

    收敛自 analytics_service.observe_patient_domain_state 与
    operations/data_export._patient_domain_mode 的逐字相同包装（批次 1，
    redundancy-review-2026-11-15）；前者保留为具名转发以维持既有导入面。
    """
    try:
        return await patient_domain_mode(db)
    except Exception:
        return fallback


def reraise_or_domain_error(error: PatientAccessError, factory) -> None:
    """is_domain_state_unavailable 分流助手：域状态不可用（503）原样透传，
    其余归属类失败交给 factory(error) 构造调用方域错误后抛出。

    收敛自消费方的 catch-all 五连模板（followup_access / patient_router /
    quality_issue_service / forms 集成侧等）：

        except PatientAccessError as error:
            if is_domain_state_unavailable(error):
                raise
            raise factory(error)

    factory 收到原始 PatientAccessError，可按 error_code 细分（如
    PATIENT_NOT_FOUND 与 PATIENT_NOT_ASSIGNED 分支）。批次 1 仅提供助手，
    既有调用点随后续波段迁移（相关服务文件属并行任务在途，禁改）。
    """
    if is_domain_state_unavailable(error):
        raise error
    raise factory(error)


async def _canonical_patient_read(operation):
    """canonical 对象读取的异常包装（与 patient_domain_mode 同款 fail-closed）。

    canonical 对象访问链路里存在二次状态读取（require_canonical），其
    PatientDomainError 与传输层 PyMongoError 若裸逃逸会成为 500；统一
    转 PatientAccessError 503 PATIENT_DOMAIN_STATE_UNAVAILABLE，语义与
    域模式读取失败一致。operation 自带 session 绑定。
    """
    try:
        return await operation()
    except PatientDomainError as error:
        raise _domain_state_unavailable(error.code) from None
    except PyMongoError as error:
        raise _domain_state_unavailable("PATIENT_DOMAIN_STATE_READ_FAILED") from error


def resolve_self_patient_id(actor, patient_id=None) -> str:
    """Resolve only the active legacy domain's explicit same-document identity.

    与域模式无关：任何模式下患者账号都只能显式请求本人 ID，医疗角色不得借
    该入口获得本人患者访问；canonical 的链接核验在其后的异步路径完成。
    T67 后本函数是 legacy 同文档语义的逐字载体：域分派的异步解析
    （resolve_self_patient_entity）的 legacy 分支与冻结消费方
    （clinical/workspace.py）仍经此处；canonical 分支不再使用同文档假设。
    """
    identifier = self_patient_id(getattr(actor, "id", None), getattr(actor, "role", None), patient_id)
    if identifier is None:
        raise PatientAccessError("无权访问该患者的数据")
    return identifier


async def _resolve_self_patient_entity(db, mode, actor, patient_id=None, *, session=None) -> str:
    """域分派已定（mode 由调用方给出）的本人实体解析；不读域状态。"""
    account_id = getattr(actor, "id", None)
    role = getattr(actor, "role", None)
    if role != "patient" or not isinstance(account_id, (str, ObjectId)) or not str(account_id):
        raise PatientAccessError("无权访问该患者的数据")
    # domain-dispatch: 迁移完成后可删
    if mode == "canonical":
        patient = await _canonical_patient_read(
            lambda: ClinicalPatientRepository(db).resolve_self(str(account_id), session=session))
        if patient is None:
            raise PatientAccessError("无权访问该患者的数据")
        resolved = str(patient["patient_id"])
        if patient_id is not None and (
                not isinstance(patient_id, (str, ObjectId)) or str(patient_id) != resolved):
            raise PatientAccessError("无权访问该患者的数据")
        return resolved
    identifier = self_patient_id(account_id, role, patient_id)
    if identifier is None:
        raise PatientAccessError("无权访问该患者的数据")
    return identifier


async def resolve_self_patient_entity(db, actor, patient_id=None, *, session=None) -> str:
    """Domain-dispatched entity resolution for a patient-role self request.

    患者角色「自取」的对象级实体解析（T67 缺陷 2：T64 登记的内核缺口收口）。
    canonical 的账号 ID 与临床患者 ID 是两个主键（显式绑定下必然不同），
    绝不能再按 legacy 同文档假设把账号 ID 当患者实体 ID 前置比较：

    - canonical：先做域无关的角色/标识校验（任何域都只有患者角色可自取），
      随后经 repo.resolve_self（verified 链接 + 账号反向复核 + active 临床
      记录）解析临床患者实体 ID；显式目标参数存在时必须与解析结果一致
      （目标缺失即本人实体）。显式绑定（账号 ID≠患者 ID）的对象级自取由此
      打通，且无链接账号绝不因 ID 巧合被放行。
    - legacy：原 self_patient_id 同文档语义逐字不变（账号 ID 即患者实体 ID，
      显式目标必须同 ID）。

    注意：目标一致性比较必须发生在域模式读取之后——同一目标在不同域的
    合法性不同，域状态不可用（503）因此优先于「显式拒绝他人 ID」（403）
    呈现，与「域状态不可用必须拒绝请求、绝不静默降级」的 fail-closed 口径
    一致。legacy 的角色/标识域无关校验仍先于域读取（任何域语义相同）。
    """
    mode = await patient_domain_mode(db, session=session)
    return await _resolve_self_patient_entity(db, mode, actor, patient_id, session=session)


async def _ensure_self_patient_access(db, mode, actor, patient_id=None, *, session=None) -> str:
    """域分派已定（mode 由调用方给出）的本人访问校验；不读域状态。"""
    identifier = await _resolve_self_patient_entity(db, mode, actor, patient_id, session=session)
    # domain-dispatch: 迁移完成后可删
    if mode == "canonical":
        return identifier
    await _load_patient_doc(db, mode, identifier, session=session)
    return identifier


async def ensure_self_patient_access(db, actor, patient_id=None, *, session=None) -> str:
    """Verify the explicit self request against the active domain.

    legacy：同一文档关系即患者实体（保持现状语义）。canonical：必须存在经
    迁移核验的 verified 账号链接（repo.resolve_self），账号 ID 不再被假定即
    患者 ID；链接缺失、停用或临床记录不可用一律拒绝。canonical 分支的
    resolve_self 已含 active 临床记录与账号反向复核，无需二次 load_patient_doc。
    """
    mode = await patient_domain_mode(db, session=session)
    return await _ensure_self_patient_access(db, mode, actor, patient_id, session=session)


def patient_assignment_field(operator_role: str) -> str:
    """使用与患者关联写入路径一致的角色字段，禁止跨角色借用关系。"""
    fields = {"doctor": "practitioners", "health_manager": "health_managers"}
    if operator_role not in fields:
        raise PatientAccessError("当前角色不能通过医护归属访问患者")
    return fields[operator_role]


def assigned_patient_query(operator_id: str, operator_role: str = "doctor") -> Dict[str, Any]:
    """与对象校验同源的患者查询范围，兼容历史 ObjectId 关系值（legacy 域）。

    同步保留：既有业务消费方直接将该查询用于 users 集合，其接入域分派属于
    后续波段。canonical 范围请使用 assigned_scope_query。
    """
    identifiers = [str(operator_id)]
    if ObjectId.is_valid(str(operator_id)):
        identifiers.append(ObjectId(str(operator_id)))
    return {"role": "patient", patient_assignment_field(operator_role): {"$in": identifiers}}


async def _assigned_scope_query(db, mode, operator_id: str, operator_role: str) -> Dict[str, Any]:
    """域分派已定（mode 由调用方给出）的归属范围构造；不读域状态。"""
    patient_assignment_field(operator_role)
    # domain-dispatch: 迁移完成后可删
    if mode == "canonical":
        return canonical_assigned_query(operator_id, operator_role)
    return assigned_patient_query(operator_id, operator_role)


async def assigned_scope_query(db, operator_id: str, operator_role: str = "doctor",
                               *, session=None) -> Dict[str, Any]:
    """按域模式返回患者归属查询范围；canonical 范围已含 status=active。

    角色校验与 legacy 同源（同一 PatientAccessError），避免两条路径的
    医护角色语义漂移。

    只构造不执行：执行载体由调用方决定（这正是早期波段「canonical 查询
    形状被交给 users 执行」载体错位缺口的根源）。需要「构造+执行」一体的
    域感知范围解析时，请使用 assigned_scope_ids。
    """
    mode = await patient_domain_mode(db, session=session)
    return await _assigned_scope_query(db, mode, operator_id, operator_role)


async def _assigned_scope_ids(db, mode, operator_id: str, operator_role: str,
                               *, session=None,
                               extra_query: Optional[Dict[str, Any]] = None) -> list:
    """域分派已定（mode 由调用方给出）的范围解析「构造+执行」一体；不读域状态。"""
    patient_assignment_field(operator_role)
    # domain-dispatch: 迁移完成后可删
    if mode == "canonical":
        repo = ClinicalPatientRepository(db)
        cursor = repo.collection.find(
            canonical_assigned_query(operator_id, operator_role), {"patient_id": 1},
            session=session)
        documents = await cursor.to_list(length=None)
        return [document["patient_id"] for document in documents]
    query = assigned_patient_query(operator_id, operator_role)
    if extra_query:
        query = {**query, **extra_query}
    return await LegacyPatientRepository(db).assigned_ids(query)


async def assigned_scope_ids(db, operator_id: str, operator_role: str = "doctor",
                             *, session=None,
                             extra_query: Optional[Dict[str, Any]] = None) -> list:
    """构造并执行一体的域感知医护范围患者 ID 解析；查询落在所在域的集合上。

    legacy：构造 assigned_patient_query（保留身份双形态与
    LegacyPatientRepository.assigned_ids 的歧义防护，PATIENT_IDENTITY_AMBIGUOUS
    503 语义逐字不变）后执行于 users。canonical：执行 repository.assigned_query
    （已含 status=active）于 clinical_patients，返回 patient_id 列表；
    canonical 患者主键由唯一索引防重，无 legacy 双形态歧义防护的对应物。

    extra_query 仅叠加于 legacy 分支的查询（legacy 专属精化条件，例如设备
    域的 is_active 过滤）；canonical 的等价可用性语义已由 assigned_query 的
    status=active 内建，不叠加 legacy 专属字段，避免把 users 形态的查询
    条件误用于 clinical_patients。
    """
    mode = await patient_domain_mode(db, session=session)
    return await _assigned_scope_ids(db, mode, operator_id, operator_role,
                                     session=session, extra_query=extra_query)


async def _load_patient_doc(db, mode, patient_id, *, session=None) -> Dict[str, Any]:
    """域分派已定（mode 由调用方给出）的患者文档读取；不读域状态。"""
    # domain-dispatch: 迁移完成后可删
    if mode == "canonical":
        doc = await _canonical_patient_read(
            lambda: ClinicalPatientRepository(db).get(patient_id, session=session))
        if doc is not None and doc.get("status") != "active":
            doc = None
    else:
        doc = await LegacyPatientRepository(db).get(patient_id, session=session)
    if not doc:
        raise PatientAccessError("患者不存在", error_code="PATIENT_NOT_FOUND",
                                 status_code=status.HTTP_404_NOT_FOUND)
    return doc


async def load_patient_doc(db: AsyncIOMotorDatabase, patient_id: str, *, session=None) -> Dict[str, Any]:
    """按 ID 加载当前域的患者文档（legacy: users；canonical: clinical_patients）。

    两种主键形态（ObjectId / 非 ObjectId 字符串）在各自域内保持兼容；
    canonical 分支不读 users。canonical 的对象级可用性由 status 承载：
    status != "active"（迁移自 legacy is_active=False 的停用患者）按不存在
    处理（404 PATIENT_NOT_FOUND），与 legacy 消费方对 is_active=False 的
    404 语义对齐——canonical 文档没有 is_active 字段，缺少此校验会让
    停用患者对所有对象级访问路径恒放行。
    """
    mode = await patient_domain_mode(db, session=session)
    return await _load_patient_doc(db, mode, patient_id, session=session)


async def _ensure_patient_access(db, mode, patient_id, operator_id, operator_role,
                                 *, session=None) -> Dict[str, Any]:
    """域分派已定（mode 由调用方给出）的患者侧关联校验；不读域状态。"""
    if operator_role == "admin":
        return {}
    field = patient_assignment_field(operator_role)
    patient = await _load_patient_doc(db, mode, patient_id, session=session)
    assignments = {str(item) for item in (patient.get(field) or [])}
    if str(operator_id) not in assignments:
        raise PatientAccessError(
            "当前用户未获分配管理该患者，无权访问该患者数据",
            error_code="PATIENT_NOT_ASSIGNED", status_code=status.HTTP_403_FORBIDDEN)
    return patient


async def ensure_patient_access(db: AsyncIOMotorDatabase, patient_id: str,
                                operator_id: str, operator_role: str, *, session=None) -> Dict[str, Any]:
    """按已认证角色校验患者侧关联；admin 沿用既有豁免。

    归属字段与比较逻辑两域同构（clinical_patients 迁移保留原归属列表与
    ID 字面量）。患者实体可用性：legacy 的 is_active 仍由各域消费方执行
    既有策略（行为不变）；canonical 的 status 校验已由 load_patient_doc
    的 canonical 分支统一执行（inactive → 404），经本函数与
    load_patient_doc 的对象级路径自动生效。
    """
    mode = await patient_domain_mode(db, session=session)
    return await _ensure_patient_access(db, mode, patient_id, operator_id,
                                        operator_role, session=session)


async def linked_account_id(db, patient_id, *, session=None) -> Optional[str]:
    """canonical 链接方向：患者实体 ID → 已核验的患者账号 ID（无链接返回 None）。

    仅认 patient_account_links 的 verified 链接（account_id / patient_id 唯一
    索引保证至多一条）；不命中返回 None，绝不推断（不猜同 ID、不做姓名/归属
    映射）。canonical 专用载体——legacy 域没有链接表，legacy 的本人身份走
    同文档语义（见 resolve_self_patient_entity）。
    """
    link = await db[ACCOUNT_LINKS].find_one(
        {"patient_id": str(patient_id), "status": "verified"}, session=session)
    return link["account_id"] if link else None


async def active_patient_ids(db, mode) -> list:
    """当前域的全部可用患者 ID（admin 全量枚举口径）。

    legacy：users + role=patient + is_active=True，经 legacy 适配器执行（保留
    身份歧义 503 防护）。canonical：clinical_patients + status=active（主键
    唯一，无 legacy 双形态歧义防护对应物）。枚举是全量只读口径，不绑定事务
    会话（调用方均为非事务的 admin 列表路径）。
    """
    # domain-dispatch: 迁移完成后可删
    if mode == "canonical":
        cursor = ClinicalPatientRepository(db).collection.find(
            {"status": "active"}, {"patient_id": 1})
        return [document["patient_id"] async for document in cursor]
    return await LegacyPatientRepository(db).assigned_ids(
        {"role": "patient", "is_active": True})


class PatientDomainContext:
    """请求内贯穿的患者域访问器：域模式只读取一次，后续访问复用同一结论。

    持有 db、已读取的 mode 与可选 session（事务内必须透传，否则状态读取
    会脱离事务快照）。患者读取、归属校验、本人解析、范围解析都走本对象，
    域分派细节不再散落到各服务层。

    canonical 对象读取在 repository 侧仍保留一次 require_canonical 二次状态
    复核——那是 canonical 一致性护栏（状态中途切换即拒绝），不是域模式分派
    读取；legacy 路径不会产生第二次状态读取。
    """

    __slots__ = ("db", "mode", "session")

    def __init__(self, db, mode, *, session=None):
        self.db = db
        self.mode = mode
        self.session = session

    @property
    def is_canonical(self) -> bool:
        # domain-dispatch: 迁移完成后可删
        return self.mode == "canonical"

    def assignment_field(self, operator_role: str) -> str:
        """使用与患者关联写入路径一致的角色字段，禁止跨角色借用关系。"""
        return patient_assignment_field(operator_role)

    def entity_id(self, document: Dict[str, Any]) -> str:
        """当前域的患者实体主键：legacy=users._id；canonical=clinical_patients.patient_id。"""
        # domain-dispatch: 迁移完成后可删
        if self.is_canonical:
            return str(document["patient_id"])
        return str(document["_id"])

    async def load_patient_doc(self, patient_id) -> Dict[str, Any]:
        return await _load_patient_doc(self.db, self.mode, patient_id, session=self.session)

    async def ensure_patient_access(self, patient_id, operator_id, operator_role) -> Dict[str, Any]:
        return await _ensure_patient_access(self.db, self.mode, patient_id, operator_id,
                                            operator_role, session=self.session)

    async def resolve_self_patient_entity(self, actor, patient_id=None) -> str:
        return await _resolve_self_patient_entity(self.db, self.mode, actor, patient_id,
                                                  session=self.session)

    async def ensure_self_patient_access(self, actor, patient_id=None) -> str:
        return await _ensure_self_patient_access(self.db, self.mode, actor, patient_id,
                                                 session=self.session)

    async def assigned_scope_query(self, operator_id, operator_role="doctor") -> Dict[str, Any]:
        return await _assigned_scope_query(self.db, self.mode, operator_id, operator_role)

    async def assigned_scope_ids(self, operator_id, operator_role="doctor", *,
                                 extra_query=None) -> list:
        return await _assigned_scope_ids(self.db, self.mode, operator_id, operator_role,
                                         session=self.session, extra_query=extra_query)

    async def linked_account_id(self, patient_id) -> Optional[str]:
        """canonical 链接方向：患者实体 ID → 已核验的患者账号 ID（仅 canonical 有意义）。"""
        return await linked_account_id(self.db, patient_id, session=self.session)

    async def active_patient_ids(self) -> list:
        """当前域的全部可用患者 ID（admin 全量枚举口径）。"""
        return await active_patient_ids(self.db, self.mode)


async def patient_domain_context(db, *, session=None) -> PatientDomainContext:
    """构造请求内贯穿的患者域访问器：域模式在此读取一次（fail-closed）。

    状态读取失败或观察到未知状态一律抛 PATIENT_DOMAIN_STATE_UNAVAILABLE
    （503）——绝不静默回退 legacy。事务内调用必须传 session，让状态读取
    落在同一事务快照内。
    """
    mode = await patient_domain_mode(db, session=session)
    return PatientDomainContext(db, mode, session=session)


async def patient_domain_context_safe(db, *, fallback: str = "unknown") -> PatientDomainContext:
    """fail-safe 口径的域上下文（统计聚合/只读导出等展示类路径专用）。

    读取失败或观察到不可用状态时 mode=fallback（默认 "unknown"），绝不猜测
    域回退。与 patient_domain_context 的 fail-closed（503 拒绝请求）刻意分化：
    unknown ≠ legacy——消费方收到 unknown 必须把患者类指标降级为不可用并如实
    标记，不得按 legacy 聚合（canonical 患者会漏算、legacy 停用患者会误算）。
    """
    mode = await patient_domain_mode_safe(db, fallback=fallback)
    return PatientDomainContext(db, mode)
