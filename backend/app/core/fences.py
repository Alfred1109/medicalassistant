"""并发栅栏载体模块（患者域第二波段拆分的预研基础层）。

## 背景：现有五类栅栏全部以 users 账号文档为载体

legacy 域中账号与患者实体同文档，`$inc` 一次命中即同时覆盖"账号态"与
"患者归属"两种语义（对照 docs/patient-domain-cutover-plan.md §3.1）：

| 栅栏字段 | 调用点 | 语义 |
|---|---|---|
| `_access_fence` | quality_issue_service.py:78-84、rehab_publication_service.py:114-122、followup_service.py:312-317 | 账号/患者并发状态 |
| `_reminder_fence` | followup_reminder_service.py:74-81、followup_service.py:342-347 | 提醒并发 |
| `_device_access_fence` | core/device_access.py:34-41 | 设备访问并发撤权 |
| `fill_use_revision` | integrations/forms/service.py:299、612-618、identity/service.py:59 | 填报凭证消费 |
| `report_access_revision` | clinical/workspace.py:472-489（含归属字段快照比较） | 报告访问并发 |

统一模式：事务内 `update_one({定位条件}, {"$inc": {栅栏字段: 1}})`，
`matched_count != 1` 即授权/归属已变化，拒绝写（CAS 语义）。

## 拆分方案（plan §3.2）：两个载体

1. `AccountFenceStore` —— 账号栅栏载体，独立 `account_fences` 集合
   （`{account_id, fence_name, count}`，(account_id, fence_name) 唯一索引）。
   承载 `fill_use_revision`、`report_access_revision` 的账号侧计数与
   `_device_access_fence` 的账号侧复核。不落在 `users` 文档上，避免污染
   canonical 模式下 `users` 的只读约定（patients/README.md:20-21）。
2. `PatientFenceStore` —— 患者实体栅栏载体，`clinical_patients` 文档上的
   `_fence_{name}` 字段（下划线前缀约定：不进入业务投影，参照
   followup_service.py:68-69 的投影排除惯例）。承载 `_access_fence`、
   `_reminder_fence` 的患者侧与 `report_access_revision` 的归属字段快照
   比较（快照字段比较仍由调用方在 extra_query 中表达）。

## 各服务替换要点（一句话级，第二波段迁移时执行）

- quality_issue_service / rehab_publication_service `_access_fence`：
  账号侧改 `AccountFenceStore.bump`，患者侧改 `PatientFenceStore.bump`
  （双载体复核用 `dual_bump`）。
- followup_reminder_service / followup_service `_reminder_fence`：
  随访来源文档自身的栅栏不动（载体不是 users），账号侧复核改
  `AccountFenceStore.bump`，患者侧改 `PatientFenceStore.bump`。
- core/device_access.py `_device_access_fence`：账号/患者两个文档各一次
  `$inc` 改为 `dual_bump`（账号载体 + 患者载体各复核一次）。
- integrations/forms/service.py `fill_use_revision`：账号侧计数改
  `AccountFenceStore.check/bump`，患者归属条件仍走 assigned_patient_query。
- clinical/workspace.py `report_access_revision`：账号字段快照比较改走
  账号载体查询 + `AccountFenceStore`，归属字段快照比较折入
  `PatientFenceStore` 的 extra_query。

## 为什么栅栏计数不迁移（plan §3.2/3.3）

计数仅作 CAS 比较用，无业务含义；切换时各载体从当前值重新起算即可。
唯一硬约束是切换窗口内旧载体停止递增，否则回拨后旧计数失效。

## 使用约束

- 所有 bump/check/dual_bump 必须在 `run_transaction`
  （app/db/transactions.py，snapshot read concern）的回调内、并透传
  session 调用；本模块不包装事务，异常抛出后由外层事务整体回滚。
- 并发正确性由唯一索引（account_fences）与 Mongo 事务（写冲突自动重试）
  保证；matched_count/expected 复核只承担"授权快照是否失效"的 CAS 判定。
- 账号授权复核（users 的 role/is_active 读取）仍在服务层；本模块只拥有
  计数器载体本身。
"""
from typing import Any, Optional, Tuple

from pymongo import ASCENDING, ReturnDocument
from pymongo.errors import PyMongoError

from app.core.exceptions import AppBaseException

ACCOUNT_FENCES = "account_fences"
PATIENT_FENCE_COLLECTION = "clinical_patients"  # 对照 app/patients/repository.py 的 PATIENTS
ACCOUNT_FENCE_INDEX_NAME = "account_fence_unique"

# $inc 打在非数值字段上时 Mongo 抛的 TypeMismatch 写错误码
_MONGO_TYPE_MISMATCH_CODE = 14


class FenceError(AppBaseException):
    """栅栏载体错误基类（错误码命名对齐现有 *_FENCE_INVALID 风格）。"""

    def __init__(self, message: str, *, error_code: str, status_code: int,
                 details: Optional[dict] = None):
        super().__init__(message=message, status_code=status_code,
                         error_code=error_code, details=details)


class FenceInvalid(FenceError):
    """栅栏字段/参数形态无效（对齐现有 *_FENCE_INVALID 503 语义）。"""

    def __init__(self, message: str, *, details: Optional[dict] = None):
        super().__init__(message, error_code="FENCE_INVALID",
                         status_code=503, details=details)


class FenceMismatch(FenceError):
    """复核失败：授权/归属已变化，必须拒绝本次写（CAS miss）。"""

    def __init__(self, message: str = "授权状态已变化，请重新加载后重试",
                 *, details: Optional[dict] = None):
        super().__init__(message, error_code="FENCE_MISMATCH",
                         status_code=409, details=details)


def _validate_fence_name(fence_name: Any) -> str:
    """栅栏名会被用作 account_fences 键值与 clinical_patients 字段名后缀。"""
    if (not isinstance(fence_name, str) or not fence_name
            or "." in fence_name or "$" in fence_name or len(fence_name) > 64):
        raise FenceInvalid("栅栏名称无效", details={"fence_name": repr(fence_name)})
    return fence_name


def _validate_expected(expected: Any) -> int:
    if type(expected) is not int or expected < 0:
        raise FenceInvalid("栅栏期望值无效", details={"expected": repr(expected)})
    return expected


def _validate_new_count(value: Any, fence_name: str) -> int:
    """递增后的计数必须是正整数（对齐现有 `type(value) is not int` 严格校验）。"""
    if type(value) is not int or value < 1:
        raise FenceInvalid("栅栏并发状态无效",
                           details={"fence_name": fence_name, "count": repr(value)})
    return value


def patient_fence_field(fence_name: str) -> str:
    """患者载体栅栏字段的命名约定（下划线前缀，不进入业务投影）。"""
    return f"_fence_{_validate_fence_name(fence_name)}"


class AccountFenceStore:
    """账号栅栏载体：account_fences 集合上的 (account_id, fence_name) 计数器。

    计数器由本模块独占管理（upsert 首插），授权状态复核（users 读取）仍在
    服务层；本载体的职责是把"账号态是否被并发改写"序列化为一次计数递增。
    """

    def __init__(self, db):
        self.db = db
        self.collection = db[ACCOUNT_FENCES]

    @staticmethod
    def _key(account_id: Any, fence_name: str) -> dict:
        if not isinstance(account_id, (str, int)) or not str(account_id):
            raise FenceInvalid("账号标识无效", details={"account_id": repr(account_id)})
        return {"account_id": str(account_id), "fence_name": fence_name}

    async def bump(self, account_id, fence_name, *, session=None) -> int:
        """无条件递增并返回新计数；计数器不存在时插入（upsert，从 1 起算）。

        用于调用方已在同一事务内重新核实授权快照、只需栅栏化的场景
        （对照现有 `document.get("_access_fence", 0)` + 无条件 $inc 的形态）。
        """
        fence_name = _validate_fence_name(fence_name)
        query = self._key(account_id, fence_name)
        # 唯一索引兜底：事务外并发 upsert 的 DuplicateKeyError 属瞬时冲突，
        # 同 session 重试即可。注意该重试循环仅在事务外有效——事务内首插冲突
        # 会中止当前事务，同 session 的下一次操作只会得到 NoSuchTransaction
        # （code != 11000，走下方 raise 原样上抛），不会进入本循环的重试语义；
        # 事务内的并发首插由 with_transaction 对整个回调的重试兜底
        # （对照 test_fences_replica_set.py 场景 4 的实测结论）。
        for _ in range(3):
            try:
                document = await self.collection.find_one_and_update(
                    query, {"$inc": {"count": 1}},
                    return_document=ReturnDocument.AFTER, upsert=True,
                    session=session)
                break
            except PyMongoError as exc:
                if getattr(exc, "code", None) != 11000:
                    raise
                document = None
        else:
            raise FenceInvalid("账号栅栏并发冲突未能解决",
                               details={"fence_name": fence_name})
        return _validate_new_count(document.get("count"), fence_name)

    async def check(self, account_id, fence_name, expected, *, session=None) -> int:
        """CAS 递增：仅当当前计数等于 expected 时递增并返回新计数。

        语义对齐现有调用点「递增失败 = 授权已变化 = 拒绝」：计数与读取时不
        一致（或计数器消失）抛 FenceMismatch，集合不做任何写入。expected=0
        表示读取时计数器尚不存在，当前仍不存在则视同首次递增（返回 1）。
        """
        fence_name = _validate_fence_name(fence_name)
        expected = _validate_expected(expected)
        query = self._key(account_id, fence_name)
        if expected == 0:
            current = await self.collection.find_one(query, {"count": 1}, session=session)
            if current is not None:
                raise FenceMismatch(details={"carrier": "account", "fence_name": fence_name})
            return await self.bump(account_id, fence_name, session=session)
        result = await self.collection.find_one_and_update(
            {**query, "count": expected}, {"$inc": {"count": 1}},
            return_document=ReturnDocument.AFTER, session=session)
        if result is None:
            raise FenceMismatch(details={"carrier": "account", "fence_name": fence_name})
        return _validate_new_count(result.get("count"), fence_name)


class PatientFenceStore:
    """患者实体栅栏载体：clinical_patients 文档上的 _fence_{name} 字段。

    与 AccountFenceStore 对称，但患者文档必须已存在（无 upsert）：文档
    缺失或 extra_query 不再匹配 = 患者归属/状态已变化，拒绝写。extra_query
    用于折入归属字段快照比较（如 practitioners/health_managers/status）。
    """

    def __init__(self, db, collection: str = PATIENT_FENCE_COLLECTION):
        self.db = db
        self.collection = db[collection]

    @staticmethod
    def _query(patient_id: Any, fence_name: str, extra_query: Optional[dict]) -> dict:
        if not isinstance(patient_id, (str, int)) or not str(patient_id):
            raise FenceInvalid("患者标识无效", details={"patient_id": repr(patient_id)})
        query = {"patient_id": str(patient_id)}
        if extra_query:
            if not isinstance(extra_query, dict):
                raise FenceInvalid("患者栅栏附加条件无效")
            # B6 防御：定位键不得被调用方的归属快照条件覆盖——否则栅栏递增会
            # 打到别的患者文档上（宁可拒绝也不静默改道）。
            if "patient_id" in extra_query:
                raise FenceInvalid("患者栅栏附加条件不得覆盖 patient_id 定位键",
                                   details={"patient_id": str(patient_id)})
            query.update(extra_query)
        return query

    async def bump(self, patient_id, fence_name, *, session=None,
                   extra_query: Optional[dict] = None) -> int:
        """定位患者文档并递增栅栏字段，返回新计数；未命中即抛 FenceMismatch。"""
        fence_name = _validate_fence_name(fence_name)
        field = patient_fence_field(fence_name)
        query = self._query(patient_id, fence_name, extra_query)
        try:
            document = await self.collection.find_one_and_update(
                query, {"$inc": {field: 1}},
                return_document=ReturnDocument.AFTER, session=session)
        except PyMongoError as exc:
            if getattr(exc, "code", None) == _MONGO_TYPE_MISMATCH_CODE:
                raise FenceInvalid("患者栅栏并发状态无效",
                                   details={"fence_name": fence_name}) from exc
            raise
        if document is None:
            raise FenceMismatch(
                "患者归属或状态已变化，请重新加载后重试",
                details={"carrier": "patient", "fence_name": fence_name})
        return _validate_new_count(document.get(field), fence_name)

    async def check(self, patient_id, fence_name, expected, *, session=None,
                    extra_query: Optional[dict] = None) -> int:
        """CAS 递增：仅当栅栏字段当前值等于 expected 时递增，否则拒绝。

        expected=0 表示读取时字段尚不存在；字段仍未出现且患者文档仍在时
        视同首次递增（返回 1），字段已出现即有人并发递增过，拒绝。
        """
        fence_name = _validate_fence_name(fence_name)
        expected = _validate_expected(expected)
        field = patient_fence_field(fence_name)
        query = self._query(patient_id, fence_name, extra_query)
        if expected == 0:
            current = await self.collection.find_one(query, {field: 1}, session=session)
            if current is None:
                raise FenceMismatch(
                    "患者归属或状态已变化，请重新加载后重试",
                    details={"carrier": "patient", "fence_name": fence_name})
            value = current.get(field)
            if value not in (None, 0):
                raise FenceMismatch(details={"carrier": "patient", "fence_name": fence_name})
            return await self.bump(patient_id, fence_name, session=session,
                                   extra_query=extra_query)
        result = await self.collection.find_one_and_update(
            {**query, field: expected}, {"$inc": {field: 1}},
            return_document=ReturnDocument.AFTER, session=session)
        if result is None:
            raise FenceMismatch(
                "患者归属或状态已变化，请重新加载后重试",
                details={"carrier": "patient", "fence_name": fence_name})
        return _validate_new_count(result.get(field), fence_name)


# dual_bump 的跳描述：(store, key, fence_name) 或 (store, key, fence_name, expected)。
# 带 expected 走 check（CAS），否则走 bump（无条件递增）。
_FenceHop = Tuple[Any, ...]


async def dual_bump(account: _FenceHop, patient: _FenceHop, *, session=None):
    """同一 session 内先账号后患者执行两跳栅栏递增（双载体复核）。

    调用方必须已在 run_transaction 回调内：本助手不开启、不包装事务，
    任一跳抛错即向上传播、由外层事务整体回滚（账号侧先递增的结果由 Mongo
    回滚保证不可见；fake 测试只验证调用序列与异常路径）。

    账号跳不支持 extra_query（account_fences 无业务快照字段）；患者跳的
    归属快照比较需折入 extra_query 时，请直接按序调用两个 store 方法。

    异常分类（B2 修复）：仅对 FenceMismatch（409 CAS miss）做 hop 标注包装；
    FenceInvalid（503，栅栏名称/期望值/载体数据损坏）原样透传——数据损坏与
    授权变化必须可区分，不得把 503 数据损坏降级为 409 失配。
    """
    def _prepare(hop, carrier):
        if not isinstance(hop, tuple) or len(hop) not in (3, 4):
            raise FenceInvalid("栅栏跳描述无效", details={"carrier": carrier})
        store, key, fence_name = hop[0], hop[1], hop[2]
        if not hasattr(store, "bump") or not hasattr(store, "check"):
            raise FenceInvalid("栅栏载体对象无效", details={"carrier": carrier})
        expected = _validate_expected(hop[3]) if len(hop) == 4 else None
        return store, key, fence_name, expected

    store, key, fence_name, expected = _prepare(account, "account")
    try:
        if expected is None:
            account_count = await store.bump(key, fence_name, session=session)
        else:
            account_count = await store.check(key, fence_name, expected, session=session)
    except FenceMismatch as exc:
        # exc.details 由 AppBaseException 归一为 dict，`or {}` 仅为防御 None 形态
        raise FenceMismatch(str(exc),
                            details={**(exc.details or {}), "hop": "account"}) from exc

    store, key, fence_name, expected = _prepare(patient, "patient")
    try:
        if expected is None:
            patient_count = await store.bump(key, fence_name, session=session)
        else:
            patient_count = await store.check(key, fence_name, expected, session=session)
    except FenceMismatch as exc:
        raise FenceMismatch(str(exc),
                            details={**(exc.details or {}), "hop": "patient"}) from exc

    return account_count, patient_count


async def create_account_fence_indexes(db) -> None:
    """声明 account_fences 唯一索引（部署侧脚本调用）。

    任何应用启动路径不得调用：沿用 create_patient_indexes 的惯例，由
    发布/迁移脚本在启用栅栏新载体前显式执行；集合不存在时 create_index
    会隐式建集合，因此必须在切换窗口前、而非进程启动时执行。
    """
    await db[ACCOUNT_FENCES].create_index(
        [("account_id", ASCENDING), ("fence_name", ASCENDING)],
        name=ACCOUNT_FENCE_INDEX_NAME, unique=True)
