"""WebSocket 端点层（api）+ 连接管理器兼容导出。

连接管理器（连接表与投递语义）已迁至中性模块 app/realtime/ws_manager.py：
services 层此前只能反向 import api 取连接管理器（方向倒挂），现已改为
只依赖中性模块。本模块保留 WS 端点注册、typing 帧复核与既有公开名字的
兼容导出（ConnectionManager / manager / get_connection_manager /
make_manager_deliverer / publish_event 等），既有导入路径与 patch 点不变。
"""
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException
from typing import Dict, List, Any, Optional, Set, Tuple
import json
import asyncio
import time
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from datetime import datetime
import logging

from app.core.auth import get_current_user_ws
from app.core.config import settings
from app.integrations.identity.access import unified_authentication
from app.db.mongodb import get_database, db as mongodb_state
from app.api.ws_event_bus import (  # noqa: F401 — publish_event 等保留为兼容导出（既有 patch 点）
    bus_enabled,
    publish_event,
    remove_presence,
    start_event_bus,
    stop_event_bus,
    upsert_presence,
)
from app.realtime.ws_manager import (
    ConnectionManager,
    get_connection_manager,
    make_manager_deliverer,
    manager,
    register_manager_provider,
)
from app.models.user import User
from app.services.communication_service import CommunicationService
from app.services.notification_service import NotificationService

# 配置日志
logger = logging.getLogger(__name__)
IDENTITY_RECHECK_SECONDS = 5

# 兼容既有运行时注入/patch 点：连接管理器由本层解析（晚绑定到本模块的
# get_connection_manager），services 侧只依赖中性模块的 resolve_connection_manager()。
register_manager_provider(lambda: get_connection_manager())

# ---------------------------------------------------------------------------
# D4（T48）：typing 帧的撤权处置
#
# 缺陷（T23 记录）：typing 帧此前仅转发不复核，非统一认证部署（无
# identity_validator 周期复核）下，连接期内被停用的账号可无限期继续向房间
# 发送 typing 帧。typing 是纯瞬态信号（WS03 冻结：不落库），但转发仍是
# 对已撤权者的房间内广播，须兜底。
#
# 权衡（按要求实现并说明）：逐帧做完整 ConversationPolicy.authorize（两次
# 查库）太贵——typing 可随按键高频发生。本实现为两层廉价复核：
# 1) 成员层：本进程聊天房连接表（纯内存，入房时已过 is_conversation_participant）；
# 2) 账号层：is_active 点查（users _id 单键查询）+ 每用户 TTL 缓存
#   （TYPING_ACCOUNT_RECHECK_SECONDS，默认 5s，对齐 IDENTITY_RECHECK_SECONDS）。
# 撤权感知的上界即 TTL（撤权后最多再转发一个 TTL 窗口内的 typing 帧，下一条
# 即 4403 断连，与 message 分支同语义）——对无持久化语义的瞬态信号可接受；
# 换取每用户每 TTL 至多一次点查。复核查库异常时按「未撤权」放行且不缓存
# （fail-open：DB 故障不等于撤权，typing 无落库语义，不得因瞬时故障断连）。
# ---------------------------------------------------------------------------
TYPING_ACCOUNT_RECHECK_SECONDS = 5
# user_id -> (缓存失效时刻 monotonic, 是否有效账号)
_typing_account_cache: Dict[str, Tuple[float, bool]] = {}


async def typing_frame_allowed(db, conversation_id: str, user_id: str) -> bool:
    """typing 帧的廉价成员 + 账号复核（D4，见上方权衡说明）。"""
    # 成员层：房间在册（免费本地检查；非成员连接不可能在房间表内发帧）
    if user_id not in get_connection_manager().chat_rooms.get(conversation_id, {}):
        return False
    # 账号层：TTL 缓存的 is_active 复核
    now = time.monotonic()
    cached = _typing_account_cache.get(user_id)
    if cached is not None and cached[0] > now:
        return cached[1]
    try:
        user = await db.users.find_one({"_id": ObjectId(user_id)})
        allowed = bool(user and user.get("is_active", False))
    except Exception as error:
        # 复核通路故障：fail-open 且不缓存（见上方权衡说明）
        logger.warning(f"typing 帧账号复核失败，按有效放行: {str(error)}")
        return True
    if len(_typing_account_cache) > 1024:
        # 惰性清理过期项，防止长期运行下的无界增长
        for stale_id, (deadline, _) in list(_typing_account_cache.items()):
            if deadline <= now:
                del _typing_account_cache[stale_id]
    _typing_account_cache[user_id] = (now + TYPING_ACCOUNT_RECHECK_SECONDS, allowed)
    return allowed


async def receive_authorized(websocket):
    """Recheck idle connections every 5s and every inbound frame; never use stale identity."""
    validator = websocket.scope.get("identity_validator")
    if validator is None:
        return await websocket.receive_text()
    while True:
        try:
            value = await asyncio.wait_for(websocket.receive_text(), timeout=IDENTITY_RECHECK_SECONDS)
        except asyncio.TimeoutError:
            if await validator():
                continue
            await websocket.close(code=4401)
            raise WebSocketDisconnect(code=4401)
        if not await validator():
            await websocket.close(code=4401)
            raise WebSocketDisconnect(code=4401)
        return value

# 在应用中注册WebSocket路由
def setup_websockets(app: FastAPI):
    # WS04：bus 模式下挂载事件总线（读侧 tailable cursor + presence 心跳）。
    # setup_websockets 由 main.py 启动序列在 connect_to_mongodb() 成功后调用，
    # 与设计稿 S1 的挂载点等价；local 模式（默认）不启动任何总线任务。
    if bus_enabled():
        async def _startup_event_bus():
            await start_event_bus(mongodb_state.db, make_manager_deliverer(manager), manager)

        app.add_event_handler("startup", _startup_event_bus)
        app.add_event_handler("shutdown", stop_event_bus)

    @app.websocket("/ws/chat/{conversation_id}")
    async def websocket_chat_endpoint(
        websocket: WebSocket,
        conversation_id: str,
        db: AsyncIOMotorClient = Depends(get_database)
    ):
        """聊天WebSocket端点"""
        user = None
        connection_id = f"conn_{datetime.now().timestamp()}"

        try:
            # 验证用户身份
            user = await get_current_user_ws(websocket, db)
            if not user:
                await websocket.close(code=1008)  # Policy violation
                return

            user_id = str(user["_id"])

            if unified_authentication():
                async def valid_identity():
                    try:
                        current = await get_current_user_ws(websocket, db)
                        return bool(current and str(current["_id"]) == user_id and
                            await CommunicationService.is_conversation_participant(db, conversation_id, user_id))
                    except Exception:
                        return False
                websocket.scope["identity_validator"] = valid_identity

            # 会话成员校验（WS02 前置）：非会话参与者拒绝入房。
            # 房间名即会话 id（/ws/chat/{conversation_id}，Mongo ObjectId 字符串），
            # 沿用现有约定，不做别名映射。
            if not await CommunicationService.is_conversation_participant(db, conversation_id, user_id):
                # 先 accept 以便投递明确错误码，再以 4403（应用定义：非会话成员）断连
                await websocket.accept()
                await websocket.send_json({
                    "type": "error",
                    "error_code": "NOT_CONVERSATION_PARTICIPANT",
                    "message": "用户不是该会话参与者",
                })
                await websocket.close(code=4403)
                logger.warning(f"User {user_id} denied joining chat room {conversation_id}: not a participant")
                return

            # 建立连接
            await manager.connect_to_chat(websocket, user_id, conversation_id, connection_id)

            # 通知聊天室中的其他用户有新用户加入
            active_users = manager.get_active_users_in_chat(conversation_id)
            await manager.send_chat_message(
                {
                    "type": "user_joined",
                    "user_id": user_id,
                    "user_name": user.get("name", "Unknown"),
                    "active_users": list(active_users),
                    "timestamp": datetime.now().isoformat()
                },
                conversation_id
            )

            # 处理消息
            try:
                while True:
                    # 接收消息
                    data = await receive_authorized(websocket)
                    message_data = json.loads(data)

                    # 根据消息类型处理
                    if message_data.get("type") == "message":
                        # 先持久化、再广播（落库失败不广播，WS03）。
                        # 广播由 CommunicationService.send_message 在落库成功后完成，
                        # 载荷携带落库文档的真实 _id 与 UTC 时间戳（不再用时间戳冒充 id）。
                        message_content = message_data.get("content", "")
                        client_message_id = message_data.get("client_message_id")  # 幂等键，可选
                        if not message_content:
                            await websocket.send_json({
                                "type": "error",
                                "error_code": "INVALID_PAYLOAD",
                                "message": "content is required",
                            })
                            continue
                        try:
                            message_response = await CommunicationService.send_message(
                                db,
                                conversation_id,
                                user_id,
                                message_content,
                                message_data.get("message_type", "text"),
                                message_data.get("attachments"),
                                message_data.get("metadata"),
                                client_message_id=client_message_id,
                            )
                        except ValueError:
                            # 非会话成员（连接期间被移出/会话不存在）：拒绝并断连
                            await websocket.send_json({
                                "type": "error",
                                "error_code": "NOT_CONVERSATION_PARTICIPANT",
                                "message": "用户不是该会话参与者",
                            })
                            manager.disconnect(user_id, connection_id)
                            await websocket.close(code=4403)
                            return
                        except Exception as e:
                            from app.core.exceptions import AppBaseException
                            if isinstance(e, AppBaseException) and e.error_code == "MESSAGE_STORAGE_UNAVAILABLE":
                                await websocket.send_json({"type": "error", "error_code": e.error_code,
                                                           "message": e.message})
                                continue
                            # 数据库失败：向发送者回错误帧，不广播
                            logger.error(f"Failed to persist chat message in conversation {conversation_id}: {str(e)}")
                            await websocket.send_json({
                                "type": "error",
                                "error_code": "MESSAGE_PERSIST_FAILED",
                                "message": "消息落库失败，请重试",
                            })
                            continue

                        # 幂等回执：告知发送者该 client_message_id 对应的服务端消息
                        # （重复投递时 message 为既有文档，载荷 id 不变）
                        await websocket.send_json({
                            "type": "message_ack",
                            "client_message_id": client_message_id,
                            "message": message_response,
                        })
                    elif message_data.get("type") == "typing":
                        # 纯瞬态信号（WS03 处置：维持仅转发，不落库）。理由：
                        # 1) "正在输入"无持久化语义，落库反而不诚实；
                        # 2) 房间内成员均已在入房时通过 is_conversation_participant
                        #    校验，转发只发生在已校验房间内，逐帧重复查库纯属浪费；
                        # 3) 前端（chatWsService.ts）明确不发送不消费该帧。
                        # D4（T48）：不落库不等于不复核——非统一认证部署无周期
                        # 身份复核，连接期内被停用的账号此前可无限期发送 typing
                        # 帧。补廉价成员 + 账号复核（TTL 缓存权衡见
                        # typing_frame_allowed）；不通过则与 message 分支同语义
                        # 拒绝并 4403 断连。
                        if not await typing_frame_allowed(db, conversation_id, user_id):
                            await websocket.send_json({
                                "type": "error",
                                "error_code": "NOT_CONVERSATION_PARTICIPANT",
                                "message": "用户不是该会话参与者",
                            })
                            manager.disconnect(user_id, connection_id)
                            await websocket.close(code=4403)
                            return
                        await manager.send_chat_message(
                            {
                                "type": "typing",
                                "user_id": user_id,
                                "user_name": user.get("name", "Unknown"),
                                "is_typing": message_data.get("is_typing", False)
                            },
                            conversation_id
                        )
                    elif message_data.get("type") == "read_receipt":
                        # WS03：已读回执真实落库。语义与 REST
                        # PUT /communications/conversations/{id}/read 一致——把本会话中
                        # 发给当前用户的所有未读消息标记已读（HTTP/WS 共用同一服务方法，
                        # DB 单一事实源）；落库成功后由服务方法向房间广播 read_receipt
                        # 帧（conversation_id/reader_id/message_ids/read_at），对方客户端
                        # 实时感知"对方已读"。落库失败回错误帧，不广播。
                        # 帧不携带消息粒度：单条已读走 REST
                        # PUT /communications/messages/{message_id}/read。
                        if not await CommunicationService.is_conversation_participant(db, conversation_id, user_id):
                            # 连接期间被移出会话：与 message 分支同语义，拒绝并断连
                            await websocket.send_json({
                                "type": "error",
                                "error_code": "NOT_CONVERSATION_PARTICIPANT",
                                "message": "用户不是该会话参与者",
                            })
                            manager.disconnect(user_id, connection_id)
                            await websocket.close(code=4403)
                            return
                        try:
                            await CommunicationService.mark_conversation_as_read(db, conversation_id, user_id)
                        except ValueError:
                            # 连接期间被移出会话或账号停用（_mark_messages_as_read 的
                            # outbound 授权 ValueError）：与 message 分支同语义，拒绝
                            # 并断连——不得映射成 READ_RECEIPT_PERSIST_FAILED 误导重试
                            # （T45/D3 修复：原实现把该路径误标为落库失败且不断连）
                            await websocket.send_json({
                                "type": "error",
                                "error_code": "NOT_CONVERSATION_PARTICIPANT",
                                "message": "用户不是该会话参与者",
                            })
                            manager.disconnect(user_id, connection_id)
                            await websocket.close(code=4403)
                            return
                        except Exception as e:
                            # 数据库失败：向发送者回错误帧，不广播
                            logger.error(f"Failed to persist read receipt in conversation {conversation_id}: {str(e)}")
                            await websocket.send_json({
                                "type": "error",
                                "error_code": "READ_RECEIPT_PERSIST_FAILED",
                                "message": "已读回执落库失败，请重试",
                            })
                            continue
            except WebSocketDisconnect:
                # 用户断开连接
                manager.disconnect(user_id, connection_id)
                # 通知其他用户
                active_users = manager.get_active_users_in_chat(conversation_id)
                await manager.send_chat_message(
                    {
                        "type": "user_left",
                        "user_id": user_id,
                        "user_name": user.get("name", "Unknown"),
                        "active_users": list(active_users),
                        "timestamp": datetime.now().isoformat()
                    },
                    conversation_id
                )
            except Exception as e:
                logger.error(f"Error in chat websocket: {str(e)}")
                manager.disconnect(user_id, connection_id)
        except Exception as e:
            logger.error(f"Error establishing chat websocket connection: {str(e)}")
            try:
                await websocket.close(code=1011)  # Internal error
            except:
                pass

    @app.websocket("/ws/notifications")
    async def websocket_notification_endpoint(
        websocket: WebSocket,
        db: AsyncIOMotorClient = Depends(get_database)
    ):
        """通知WebSocket端点"""
        user = None
        connection_id = f"notif_{datetime.now().timestamp()}"

        try:
            # 验证用户身份
            user = await get_current_user_ws(websocket, db)
            if not user:
                await websocket.close(code=1008)  # Policy violation
                return

            user_id = str(user["_id"])

            if unified_authentication():
                async def valid_identity():
                    try:
                        current = await get_current_user_ws(websocket, db)
                        return bool(current and str(current["_id"]) == user_id)
                    except Exception:
                        return False
                websocket.scope["identity_validator"] = valid_identity

            # 建立连接
            await manager.connect_to_notifications(websocket, user_id, connection_id)

            # 发送初始未读通知数量
            unread_count = await NotificationService.get_unread_count(db, user_id)
            await manager._send_authorized(websocket, user_id, connection_id, {
                "type": "notification_count",
                "count": unread_count
            })

            # 处理消息
            try:
                while True:
                    # 保持连接活跃，接收可能的客户端消息
                    data = await receive_authorized(websocket)
                    # 这里可以处理客户端发送的配置消息，如通知设置等
            except WebSocketDisconnect:
                # 用户断开连接
                manager.disconnect(user_id, connection_id)
            except Exception as e:
                logger.error(f"Error in notification websocket: {str(e)}")
                manager.disconnect(user_id, connection_id)
        except Exception as e:
            logger.error(f"Error establishing notification websocket connection: {str(e)}")
            try:
                await websocket.close(code=1011)  # Internal error
            except:
                pass

    # 添加其他WebSocket端点...
