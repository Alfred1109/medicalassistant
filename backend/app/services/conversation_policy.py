"""
ConversationPolicy：会话访问策略（WS01 盘点 D3 冻结，默认采纳、待评审追认 2026-11-09）。

盘点推荐（docs/wp5-ws01-message-structure-inventory-2026-11-07.md §4.2 D3）：
入房 / 入站 / 出站三层校验同一规则——有效账号 + 会话参与者 + 授权版本匹配。

本次落地范围：
- 第 1 层「会话参与者」：完全落地，HTTP 与 WS 复用同一判定
  （WS 入房沿用 CommunicationService.is_conversation_participant）。
- 第 2 层「有效账号」：参与者存在且 is_active 才放行，覆盖连接期内账号
  被停用的入站写路径（账号停用后 send/delete 即拒绝）。
- 第 3 层「授权版本匹配」：会话文档尚无授权版本字段、断连时限数值待安全
  确认（盘点原文即标注待确认）——本层恒通过，不做伪造语义，待评审追认后
  由 WS02 落地；连接期定时复核与撤权断连时限同属 WS02 范畴。

成员模型兼容读（D1 目标形态）：participants: [{user_id, role, joined_at}] 数组；
现行写入仍为结构 B 的 participant1_id/participant2_id 双人形态，读取两者兼容。
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

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


class ConversationPolicy:
    """入房/入站/出站共用的会话访问策略（同一规则对象，三层同一判定）。"""

    @staticmethod
    async def authorize(
        db: Any,
        conversation_id: str,
        user_id: str,
        *,
        layer: str = "inbound",
    ) -> PolicyDecision:
        """校验 user_id 能否在 layer 层访问 conversation_id。

        layer 仅用于审计语义（join/inbound/outbound），当前三层规则一致；
        校验失败一律返回否定判定（不抛异常），由调用方决定对外错误形态。
        """
        # 入参合法性：无效 id 视为非成员，不区分原因（供握手阶段安全调用）
        if not ObjectId.is_valid(conversation_id) or not ObjectId.is_valid(user_id):
            return PolicyDecision(False, REASON_NOT_PARTICIPANT)

        conversation = await db.conversations.find_one({"_id": ObjectId(conversation_id)})
        if not conversation:
            return PolicyDecision(False, REASON_NOT_PARTICIPANT)
        # 第 1 层：会话参与者（D1 兼容读两种成员形态）
        if user_id not in participant_ids(conversation):
            return PolicyDecision(False, REASON_NOT_PARTICIPANT)

        # 第 2 层：有效账号（存在且启用；连接期内被停用即拒绝入站写）
        user = await db.users.find_one({"_id": ObjectId(user_id)})
        if not user or not user.get("is_active", False):
            return PolicyDecision(False, REASON_ACCOUNT_INVALID)

        # 第 3 层：授权版本匹配——待评审（无字段、无数值依据，不造），恒通过。
        return PolicyDecision(True, "", conversation)
