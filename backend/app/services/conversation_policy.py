"""会话策略：成员和账号有效性检查，并为医患写入校验当前管理关系。

医患入站写（发送消息）在事务中对实际账号、患者实体和 verified link 文档
写入栅栏；并发撤权必须写入同一文档，因此事务冲突后重试并按新关系拒绝。
关系撤销后保留已建立会话及历史读取，但禁止双方继续发送。其他角色组合沿用
原有成员与有效账号策略。

成员模型兼容读 participants 数组，以及 participant1_id/participant2_id 双人形态。
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from types import SimpleNamespace

from bson import ObjectId

# 拒绝原因码（沿用 websockets 层既有错误码命名风格）
REASON_NOT_PARTICIPANT = "NOT_CONVERSATION_PARTICIPANT"
REASON_ACCOUNT_INVALID = "ACCOUNT_INVALID"


@dataclass(frozen=True)
class PolicyDecision:
    """策略判定结果。conversation 为已取到的会话文档（供调用方复用，避免二次查询）。"""

    allowed: bool
    reason: str = ""
    conversation: Optional[Dict[str, Any]] = field(default=None, repr=False)
    care_relationship: bool = False


def participant_ids(conversation: Dict[str, Any]) -> List[str]:
    """从会话文档提取成员 id 列表（D1 兼容读：participants 数组优先，回落双人字段）。"""
    participants = conversation.get("participants")
    if isinstance(participants, list) and participants:
        return [
            str(member["user_id"])
            for member in participants
            if isinstance(member, dict) and member.get("user_id")
        ]
    ids: List[str] = []
    for key in ("participant1_id", "participant2_id"):
        value = conversation.get(key)
        if value:
            ids.append(str(value))
    return ids


def care_pair_marker_present(conversation):
    snapshot = conversation.get("participant_roles")
    if not isinstance(snapshot, dict):
        snapshot = {}
    return (conversation.get("communication_scope") == "patient_staff"
            or ("patient" in snapshot.values()
                and any(role in {"doctor", "health_manager"} for role in snapshot.values())))


class ConversationPolicy:
    """入房/入站/出站共用的会话访问策略（同一规则对象，三层同一判定）。"""

    @staticmethod
    async def _authorize_patient_staff_pair(db, conversation, *, session=None,
                                            write_fences=False) -> bool:
        """医患入站写必须仍有当前归属；读历史不调用此关系门槛。

        写事务会更新会话授权所依赖的实际账号、患者实体和 verified link 文档。
        撤权路径若并发更新任一文档，Mongo 会中止本事务并重试回调，重试时按
        新归属重新判定，不允许 snapshot 读旧授权后提交新消息。
        """
        members = participant_ids(conversation)
        if len(members) != 2:
            return False

        from app.core.patient_access import (
            PatientAccessError, ensure_patient_access, ensure_self_patient_access,
            load_patient_doc, patient_domain_mode,
        )
        from app.core.patient_identity import identity_key, load_identity_groups
        from app.core.fences import PatientFenceStore
        from app.patients.repository import ACCOUNT_LINKS

        groups = await load_identity_groups(db, members, session=session)
        accounts = []
        for identifier in members:
            documents = groups.get(identity_key(identifier), [])
            if len(documents) != 1:
                return False
            account = documents[0]
            if account.get("is_active", True) is not True:
                return False
            accounts.append((str(account["_id"]), account))

        patients = [(identifier, account) for identifier, account in accounts
                    if account.get("role") == "patient"]
        practitioners = [(identifier, account) for identifier, account in accounts
                         if account.get("role") in {"doctor", "health_manager"}]
        if len(patients) != 1 or len(practitioners) != 1:
            return False

        patient_account_id, patient_account = patients[0]
        practitioner_id, practitioner = practitioners[0]
        patient_actor = SimpleNamespace(id=patient_account["_id"], role="patient")
        try:
            patient_id = await ensure_self_patient_access(db, patient_actor, session=session)
            patient = await ensure_patient_access(
                db, patient_id, practitioner_id, practitioner["role"], session=session)
        except PatientAccessError as error:
            if error.status_code in {403, 404}:
                return False
            raise
        if not write_fences:
            return True

        # Account deactivation/role changes update these same user records.
        for account_id, account in ((patient_account_id, patient_account),
                                    (practitioner_id, practitioner)):
            changed = await db.users.update_one(
                {"_id": account["_id"], "role": account["role"], "is_active": {"$ne": False}},
                {"$inc": {"_communication_access_fence": 1}}, session=session)
            if changed.matched_count != 1:
                return False

        if await patient_domain_mode(db, session=session) == "canonical":
            await PatientFenceStore(db).bump(
                patient_id, "communication_access", session=session)
            link = await db[ACCOUNT_LINKS].find_one(
                {"account_id": patient_account_id, "patient_id": str(patient_id),
                 "status": "verified"}, session=session)
            if not link:
                return False
            changed = await db[ACCOUNT_LINKS].update_one(
                {"_id": link["_id"], "account_id": patient_account_id,
                 "patient_id": str(patient_id), "status": "verified"},
                {"$inc": {"communication_access_fence": 1}}, session=session)
            if changed.matched_count != 1:
                return False
        else:
            # In legacy mode the patient entity/account is one users document.
            changed = await db.users.update_one(
                {"_id": patient["_id"], "role": "patient", "is_active": {"$ne": False}},
                {"$inc": {"_communication_access_fence": 1}}, session=session)
            if changed.matched_count != 1:
                return False
        return True

    @staticmethod
    async def mark_care_conversations_before_role_change(db, account, previous_role, *, session):
        """Persist role evidence for every currently identifiable care conversation.

        Caller runs this and the role update in one transaction. The same account
        and conversation documents are also written by send_message transactions,
        so a concurrent send or role change is ordered by Mongo write conflicts.
        """
        identifier = str(account["_id"])
        cursor = db.conversations.find({"$or": [
            {"participant1_id": identifier}, {"participant2_id": identifier},
            {"participants.user_id": identifier},
        ]}, session=session)
        conversations = await cursor.to_list(length=None)
        from app.core.exceptions import AppBaseException
        from app.core.patient_identity import identity_key, load_identity_groups

        for conversation in conversations:
            members = participant_ids(conversation)
            if len(members) != 2 or identifier not in members:
                continue
            counterpart_id = next(member for member in members if member != identifier)
            groups = await load_identity_groups(db, [counterpart_id], session=session)
            counterpart_rows = groups.get(identity_key(counterpart_id), [])
            if len(counterpart_rows) > 1:
                raise AppBaseException(
                    "会话对方账号标识存在歧义，无法安全变更角色", status_code=503,
                    error_code="COMMUNICATION_ROLE_CHANGE_AMBIGUOUS")
            if not counterpart_rows:
                continue
            counterpart = counterpart_rows[0]
            roles = [previous_role, counterpart.get("role")]
            care_pair = ("patient" in roles
                         and any(role in {"doctor", "health_manager"} for role in roles))
            existing_snapshot = conversation.get("participant_roles")
            if not isinstance(existing_snapshot, dict):
                existing_snapshot = {}
            existing_care = (conversation.get("communication_scope") == "patient_staff"
                             or ("patient" in existing_snapshot.values()
                                 and any(role in {"doctor", "health_manager"}
                                         for role in existing_snapshot.values())))
            if care_pair or existing_care:
                role_snapshot = dict(existing_snapshot)
                role_snapshot.setdefault(identifier, previous_role)
                role_snapshot.setdefault(counterpart_id, counterpart.get("role"))
                await db.conversations.update_one(
                    {"_id": conversation["_id"]},
                    {"$set": {"communication_scope": "patient_staff",
                              "participant_roles": role_snapshot}},
                    session=session)

    @staticmethod
    async def authorize(
        db: Any,
        conversation_id: str,
        user_id: str,
        *,
        layer: str = "inbound",
        session: Any = None,
    ) -> PolicyDecision:
        """校验成员访问权限；医患历史读取保留，入站写必须仍有当前管理关系。

        session 是 send_message 在事务内复核权限并写入关系栅栏的 Mongo 会话。
        其他层和非医患会话沿用成员与账号有效性检查。
        """
        # 入参合法性：无效 id 视为非成员，不区分原因（供握手阶段安全调用）
        if not ObjectId.is_valid(conversation_id) or not ObjectId.is_valid(user_id):
            return PolicyDecision(False, REASON_NOT_PARTICIPANT)

        kwargs = {"session": session} if session is not None else {}
        conversation = await db.conversations.find_one({"_id": ObjectId(conversation_id)}, **kwargs)
        if not conversation:
            return PolicyDecision(False, REASON_NOT_PARTICIPANT)
        # 第 1 层：会话参与者（D1 兼容读两种成员形态）
        if user_id not in participant_ids(conversation):
            return PolicyDecision(False, REASON_NOT_PARTICIPANT)

        # 第 2 层：有效账号（存在且启用；连接期内被停用即拒绝入站写）。
        # 账号身份是会话成员的权威（app/patients/README.md：会话成员 ID 保持
        # 账号 ID，不批量重写为患者 ID），本层账号语义保持不动；canonical
        # 波段需经 patient_account_links 解析账号↔患者实体。
        user = await db.users.find_one({"_id": ObjectId(user_id)}, **kwargs)
        if not user or not user.get("is_active", False):
            return PolicyDecision(False, REASON_ACCOUNT_INVALID)

        members = participant_ids(conversation)
        from app.core.patient_identity import identity_key, load_identity_groups
        identity_groups = await load_identity_groups(db, members, session=session)
        roles_by_id = {}
        ambiguous_member = False
        for member_id in members:
            accounts = identity_groups.get(identity_key(member_id), [])
            if len(accounts) > 1:
                ambiguous_member = True
                roles_by_id[member_id] = None
            else:
                roles_by_id[member_id] = accounts[0].get("role") if accounts else None
        if ambiguous_member and layer == "inbound":
            return PolicyDecision(False, REASON_NOT_PARTICIPANT, conversation)
        roles = list(roles_by_id.values())
        current_care_pair = (len(roles) == 2 and "patient" in roles
                             and any(role in {"doctor", "health_manager"} for role in roles))
        role_snapshot = conversation.get("participant_roles")
        if not isinstance(role_snapshot, dict):
            role_snapshot = {}
        snapshot_care_pair = ("patient" in role_snapshot.values()
                              and any(role in {"doctor", "health_manager"}
                                      for role in role_snapshot.values()))
        care_pair = (current_care_pair or snapshot_care_pair
                     or conversation.get("communication_scope") == "patient_staff")
        if current_care_pair and not care_pair_marker_present(conversation):
            await db.conversations.update_one(
                {"_id": conversation["_id"]},
                {"$set": {"communication_scope": "patient_staff",
                          "participant_roles": roles_by_id}},
                **kwargs)
            conversation["communication_scope"] = "patient_staff"
            conversation["participant_roles"] = roles_by_id
        if layer == "inbound" and care_pair:
            allowed = await ConversationPolicy._authorize_patient_staff_pair(
                db, conversation, session=session, write_fences=session is not None)
            if not allowed:
                return PolicyDecision(False, REASON_NOT_PARTICIPANT, conversation, True)

        # Other conversation types keep the existing member/active-account policy.
        return PolicyDecision(True, "", conversation, care_pair)

    @staticmethod
    async def send_capability(db: Any, conversation_id: str, user_id: str) -> Dict[str, Any]:
        """Return the current write capability through the same policy as send_message.

        Conversation reads deliberately remain available after care assignment
        revocation. This status is a UI hint; send_message still rechecks the same
        policy in its write path and transaction.
        """
        decision = await ConversationPolicy.authorize(
            db, conversation_id, user_id, layer="inbound")
        if decision.allowed and decision.conversation is not None:
            return {"can_send": True, "send_block_reason": None}
        if decision.care_relationship:
            reason = "care_relationship_ended"
        elif decision.reason == REASON_ACCOUNT_INVALID:
            reason = "account_invalid"
        else:
            reason = "access_unavailable"
        return {"can_send": False, "send_block_reason": reason}
