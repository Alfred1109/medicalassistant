"""医患通信/通知：连接期撤权、多进程分发与幂等专项（真实副本集门控）。

T23 待验证项落地（架构收敛记录「通信」条目）：
- 连接期撤权：会话进行中停用参与者账号（directory.set_account_active 落库路径）
  后——统一认证模式由连接的周期身份复核把连接摘除（4401）；非统一认证模式
  （无 identity_validator）由每条消息的 ConversationPolicy.authorize 实时查库
  拒绝（NOT_CONVERSATION_PARTICIPANT + 4403）。两条路径按现有实现语义分别断言。
- 多 worker 分发：两个独立 AsyncIOMotorClient 模拟两进程，bus 模式经 ws_events
  capped 总线 + tailable cursor 跨进程投递聊天帧与通知帧（先读代码确定的机制）；
  离线通知按现有语义落在重连时的未读数初始帧 + REST 拉取。
- 消息幂等：同一 (会话, client_message_id) 经两条连接并发首写，唯一索引兜底
  恰好一封落库；跨连接重复投递返回既有消息。
- 已知缺陷如实记录（不修复大改）：send_message 的授权→落库段不在事务内，
  授权通过后、插入完成前的并发停用不回滚写入（见
  RevocationRaceWindowDocumentationTests）；bus 模式下携带 server_seq 的聊天帧
  超出 BSON int64 上限发布失败、退回本进程直投（见
  CrossWorkerDistributionTests，修复建议随报告给出）。

WS 端点形态：直接驱动 setup_websockets 注册的真实端点协程（真实 ConnectionManager、
CommunicationService、ConversationPolicy、通知与身份复核路径），传输层用单事件
循环内的队列替身——生产单 worker 下所有连接本就共享同一 loop 与连接管理器，
TestClient 的 per-session portal 反而会引入跨 loop 的 motor 客户端复用问题。
门控惯例参照 test_communication_storage_mongo.py /
test_device_mutation_transactions.py：REHAB_TEST_COMM_REVOCATION_URI 指向隔离
本地副本集，每个用例独立随机库（rehab_comm_revocation_ 前缀），结束即删。
"""
import asyncio
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlsplit
from uuid import uuid4

from bson import ObjectId
from fastapi import FastAPI
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection

from app.api.websockets import (
    ConnectionManager,
    get_connection_manager,
    make_manager_deliverer,
    setup_websockets,
)
from app.api.ws_event_bus import (
    WS_EVENTS_COLLECTION,
    EventBusReader,
    configure_bus,
    ensure_ws_collections,
    reset_bus,
)
from app.core.config import settings
from app.directory.records import set_account_active
from app.services.communication_service import CommunicationService
from app.services.conversation_policy import REASON_ACCOUNT_INVALID, ConversationPolicy
from app.services.notification_service import NotificationService

URI = os.getenv('REHAB_TEST_COMM_REVOCATION_URI')


def _require_local(uri):
    if urlsplit(uri).hostname not in {'127.0.0.1', 'localhost', '::1'}:
        raise RuntimeError('Only disposable local Mongo is allowed')


class FakeWebSocket:
    """端点级传输替身：scope/收发队列/close 语义对齐 ASGI WebSocket。"""

    def __init__(self):
        self.scope = {}
        self.incoming = asyncio.Queue()
        self.frames = []
        self.cursor = 0  # 已消费帧游标（按序断言用）
        self.accepted = False
        self.close_code = None
        self.closed = asyncio.Event()

    async def accept(self):
        self.accepted = True

    async def send_json(self, message):
        self.frames.append(message)

    async def receive_text(self):
        return await self.incoming.get()

    async def close(self, code=1000):
        self.close_code = code
        self.closed.set()

    def send_frame(self, payload):
        """模拟客户端发帧（端点侧 receive_text 读到的 JSON 文本）。"""
        self.incoming.put_nowait(json.dumps(payload))


class FakeManagerSocket:
    """manager 级测试替身（参照 test_ws_event_bus_contract.py 的最小形状）。"""

    def __init__(self):
        self.sent = []
        self.scope = {}
        self.closed = False

    async def accept(self):
        pass

    async def send_json(self, message):
        self.sent.append(message)


@unittest.skipUnless(URI, 'isolated Mongo URI required')
class ReplicaCase(unittest.IsolatedAsyncioTestCase):
    """两个独立 AsyncIOMotorClient 模拟两个进程共享同一副本集数据库。"""

    async def asyncSetUp(self):
        _require_local(URI)
        self.db_name = 'rehab_comm_revocation_' + uuid4().hex
        self.client_a = AsyncIOMotorClient(URI, serverSelectionTimeoutMS=3000)
        self.client_b = AsyncIOMotorClient(URI, serverSelectionTimeoutMS=3000)
        self.db_a = self.client_a[self.db_name]
        self.db_b = self.client_b[self.db_name]
        self.alice_id, self.bob_id = str(ObjectId()), str(ObjectId())
        self.cid = str(ObjectId())
        await self.db_a.users.insert_many([
            {'_id': ObjectId(self.alice_id), 'name': 'Alice', 'role': 'doctor', 'is_active': True},
            {'_id': ObjectId(self.bob_id), 'name': 'Bob', 'role': 'patient', 'is_active': True},
        ])
        await self.db_a.conversations.insert_one({
            '_id': ObjectId(self.cid),
            'participant1_id': self.alice_id,
            'participant2_id': self.bob_id,
        })
        self._clear_manager()

    async def asyncTearDown(self):
        self._clear_manager()
        await self.client_a.drop_database(self.db_name)
        self.client_a.close()
        self.client_b.close()

    @staticmethod
    def _clear_manager():
        """隔离全局连接管理器（ConnectionManager 是模块级单例）。"""
        manager = get_connection_manager()
        manager.active_connections.clear()
        manager.chat_rooms.clear()
        manager.notification_connections.clear()
        manager.presence_rooms_cache.clear()

    async def _wait_for(self, predicate, timeout=8.0, interval=0.02):
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            if predicate():
                return
            await asyncio.sleep(interval)
        self.fail('condition not met within timeout')

    async def _cancel(self, *tasks):
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


class EndpointHarness:
    """真实 WS 端点协程驱动（单 loop，无 portal）。"""

    def build_app(self):
        self.app = FastAPI()
        setup_websockets(self.app)
        routes = {getattr(route, 'path', None): getattr(route, 'endpoint', None)
                  for route in self.app.routes}
        self.chat_endpoint = routes['/ws/chat/{conversation_id}']
        self.notif_endpoint = routes['/ws/notifications']
        self.ws_user_id = self.alice_id

    def start_identity(self, unified):
        """以真实令牌路径语义注入身份：实时查 users 行，停用/缺失返回 None。

        unified=True 时端点注册 identity_validator（周期 + 逐帧复核），
        unified=False 时与默认部署一致（validator 为 None，无周期复核）。
        """
        async def lookup(websocket, db):
            doc = await db.users.find_one({'_id': ObjectId(self.ws_user_id)})
            if doc is None or not doc.get('is_active', True):
                return None
            return doc
        identity_patch = patch('app.api.websockets.get_current_user_ws', new=lookup)
        identity_patch.start()
        self.addCleanup(identity_patch.stop)
        if unified:
            unified_patch = patch('app.api.websockets.unified_authentication', return_value=True)
            unified_patch.start()
            self.addCleanup(unified_patch.stop)

    def pin_recheck_seconds(self, value):
        """加速周期复核时钟（分支语义不变，仅缩短等待）。"""
        recheck_patch = patch('app.api.websockets.IDENTITY_RECHECK_SECONDS', value)
        recheck_patch.start()
        self.addCleanup(recheck_patch.stop)

    async def open_chat(self, db):
        """建立一条真实端点连接并等到入房广播完成，返回 (websocket, task)。"""
        ws = FakeWebSocket()
        task = asyncio.create_task(self.chat_endpoint(ws, self.cid, db))
        await self._wait_for(lambda: ws.accepted and ws.cursor < len(ws.frames))
        return ws, task

    @staticmethod
    async def next_frame(ws, frame_type=None, timeout=5.0):
        """按序消费下一帧；frame_type 给定时跳过不匹配帧（游标推进）。"""
        async def find():
            while True:
                while ws.cursor < len(ws.frames):
                    frame = ws.frames[ws.cursor]
                    ws.cursor += 1
                    if frame_type is None or frame['type'] == frame_type:
                        return frame
                await asyncio.sleep(0.02)
        return await asyncio.wait_for(find(), timeout)

    async def business_frame(self, ws, timeout=5.0):
        """按序跳过 user_joined 帧取下一个业务帧。"""
        async def find():
            while True:
                while ws.cursor < len(ws.frames):
                    frame = ws.frames[ws.cursor]
                    ws.cursor += 1
                    if frame.get('type') != 'user_joined':
                        return frame
                await asyncio.sleep(0.02)
        return await asyncio.wait_for(find(), timeout)

    async def send_message_and_collect(self, ws, content, client_message_id):
        """发一条消息帧并按序收取（广播帧, 幂等回执帧），返回回执。"""
        ws.send_frame({'type': 'message', 'content': content,
                       'client_message_id': client_message_id})
        broadcast = await self.business_frame(ws)
        self.assertEqual(broadcast['type'], 'message')
        self.assertEqual(broadcast['message']['content'], content)
        ack = await self.next_frame(ws, 'message_ack')
        self.assertEqual(ack['client_message_id'], client_message_id)
        return ack


# ---------------------------------------------------------------------------
# 场景 1：连接期撤权（真实端点 + 真实落库路径）
# ---------------------------------------------------------------------------

class ChatConnectionRevocationTests(EndpointHarness, ReplicaCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.build_app()
        mode_patch = patch.object(settings, 'EVENT_BUS_MODE', 'local')
        mode_patch.start()
        self.addCleanup(mode_patch.stop)

    async def test_revoked_account_connection_removed_by_identity_recheck_on_next_frame(self):
        """统一认证模式：停用后下一帧被周期身份复核摘除（4401），不再进入消息处理。"""
        self.start_identity(unified=True)
        self.pin_recheck_seconds(2)
        ws, task = await self.open_chat(self.db_a)
        try:
            ack = await self.send_message_and_collect(ws, 'before', 'm1')
            # 会话进行中停用（system_admin → directory.set_account_active 同一路径）
            await set_account_active(self.db_a, self.alice_id, False)
            ws.send_frame({'type': 'message', 'content': 'after', 'client_message_id': 'm2'})
            await asyncio.wait_for(ws.closed.wait(), 5)
            self.assertEqual(ws.close_code, 4401)
            # m2 未落库：撤权立即生效，无"复核间隔内仍可写"窗口（入站写每条实时查库）
            self.assertEqual(await self.db_a.messages.count_documents({}), 1)
            self.assertEqual(ack['message']['content'], 'before')
        finally:
            await self._cancel(task)

    async def test_revoked_account_idle_connection_closed_by_periodic_recheck(self):
        """统一认证模式：停用后不发任何帧，空闲周期复核到期即把连接摘除。"""
        self.start_identity(unified=True)
        self.pin_recheck_seconds(0.4)
        ws, task = await self.open_chat(self.db_a)
        try:
            await set_account_active(self.db_a, self.alice_id, False)
            await asyncio.wait_for(ws.closed.wait(), 5)
            self.assertEqual(ws.close_code, 4401)
            self.assertEqual(await self.db_a.messages.count_documents({}), 0)
        finally:
            await self._cancel(task)

    async def test_revoked_account_next_message_rejected_by_per_message_authorize(self):
        """非统一认证模式（默认部署）：无周期复核，但每条消息实时查库拒绝并断连 4403。"""
        self.start_identity(unified=False)
        ws, task = await self.open_chat(self.db_a)
        try:
            await self.send_message_and_collect(ws, 'before', 'm1')
            await set_account_active(self.db_a, self.alice_id, False)
            ws.send_frame({'type': 'message', 'content': 'after', 'client_message_id': 'm2'})
            error = await self.next_frame(ws, 'error')
            self.assertEqual(error['error_code'], 'NOT_CONVERSATION_PARTICIPANT')
            await asyncio.wait_for(ws.closed.wait(), 5)
            self.assertEqual(ws.close_code, 4403)
            self.assertEqual(await self.db_a.messages.count_documents({}), 1)
            self.assertIsNone(await self.db_a.messages.find_one({'content': 'after'}))
        finally:
            await self._cancel(task)

    async def test_revoked_account_read_receipt_rejected_without_disconnect(self):
        """非统一认证模式：停用账号的 read_receipt 写被拒（safe），但错误码语义失真。

        已知缺陷（低危）：read_receipt 分支的前置校验只有成员层
        （is_conversation_participant 不含账号层），账号停用后请求穿透到
        _mark_messages_as_read 的 outbound 授权，ValueError 被捕获后映射成
        READ_RECEIPT_PERSIST_FAILED（"落库失败请重试"），且连接不断开。
        固化现状：写入被拒、已读状态不变；修复错误码映射时须更新本用例。
        """
        self.start_identity(unified=False)
        ws, task = await self.open_chat(self.db_a)
        try:
            await self.send_message_and_collect(ws, 'before', 'm1')
            await set_account_active(self.db_a, self.alice_id, False)
            ws.send_frame({'type': 'read_receipt'})
            error = await self.next_frame(ws, 'error')
            self.assertEqual(error['error_code'], 'READ_RECEIPT_PERSIST_FAILED')
            # 连接未被摘除：下一条消息仍走消息分支的账号层拒绝 + 4403 断连
            ws.send_frame({'type': 'message', 'content': 'after', 'client_message_id': 'm2'})
            rejected = await self.next_frame(ws, 'error')
            self.assertEqual(rejected['error_code'], 'NOT_CONVERSATION_PARTICIPANT')
            await asyncio.wait_for(ws.closed.wait(), 5)
            self.assertEqual(ws.close_code, 4403)
        finally:
            await self._cancel(task)
        message = await self.db_a.messages.find_one({'client_message_id': 'm1'})
        self.assertFalse(message['read'])

    async def test_revoked_account_cannot_reconnect(self):
        """撤权后重新建立连接：身份解析返回 None，握手即被拒（1008）。"""
        self.start_identity(unified=False)
        await set_account_active(self.db_a, self.alice_id, False)
        ws = FakeWebSocket()
        task = asyncio.create_task(self.chat_endpoint(ws, self.cid, self.db_a))
        try:
            await asyncio.wait_for(ws.closed.wait(), 5)
            self.assertFalse(ws.accepted)
            self.assertEqual(ws.close_code, 1008)
            self.assertEqual(await self.db_a.messages.count_documents({}), 0)
        finally:
            await self._cancel(task)


# ---------------------------------------------------------------------------
# 场景 3：消息幂等跨连接（真实端点，两条连接共享单 worker 语义）
# ---------------------------------------------------------------------------

class CrossConnectionIdempotencyTests(EndpointHarness, ReplicaCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.build_app()
        self.start_identity(unified=False)
        mode_patch = patch.object(settings, 'EVENT_BUS_MODE', 'local')
        mode_patch.start()
        self.addCleanup(mode_patch.stop)

    async def test_duplicate_client_message_id_across_two_connections_returns_same_message(self):
        """同一幂等键先后经两条连接投递：均返回既有消息，仅一封落库。"""
        ws1, task1 = await self.open_chat(self.db_a)
        ws2, task2 = await self.open_chat(self.db_a)
        try:
            await self.send_message_and_collect(ws1, 'once', 'shared-key')
            ws2.send_frame({'type': 'message', 'content': 'once',
                            'client_message_id': 'shared-key'})
            # 重复投递走幂等快路径：ws2 收到的回执即既有消息，无二次广播/落库
            ack2 = await self.next_frame(ws2, 'message_ack')
        finally:
            await self._cancel(task1, task2)
        ack1 = await self.db_a.messages.find_one({'client_message_id': 'shared-key'})
        self.assertEqual(ack2['message']['id'], str(ack1['_id']))
        self.assertEqual(await self.db_a.messages.count_documents({}), 1)
        # 接收者离线：恰好一次离线通知副作用
        self.assertEqual(await self.db_a.notifications.count_documents({}), 1)

    async def test_concurrent_first_writes_from_two_connections_deduplicated(self):
        """同一幂等键经两条连接并发首写：唯一索引兜底，恰好一封成功。"""
        ws1, task1 = await self.open_chat(self.db_a)
        ws2, task2 = await self.open_chat(self.db_a)
        try:
            # 两连接同时投递（同一 worker 内并发，与生产多连接形态一致）
            ws1.send_frame({'type': 'message', 'content': '并发首写',
                            'client_message_id': 'race-key'})
            ws2.send_frame({'type': 'message', 'content': '并发首写',
                            'client_message_id': 'race-key'})
            ack1 = await self.next_frame(ws1, 'message_ack')
            ack2 = await self.next_frame(ws2, 'message_ack')
        finally:
            await self._cancel(task1, task2)
        self.assertEqual(ack1['message']['id'], ack2['message']['id'])
        self.assertEqual(await self.db_a.messages.count_documents({}), 1)
        self.assertEqual(await self.db_a.notifications.count_documents({}), 1)


# ---------------------------------------------------------------------------
# 场景 1/4（服务层）：策略分层拒绝 + 撤权竞态窗口现状固化
# ---------------------------------------------------------------------------

class ServiceLayerRevocationTests(ReplicaCase):
    async def test_revoked_account_rejected_at_policy_and_send_paths(self):
        """账号层撤权：成员层不变，入站授权拒绝，send_message 抛 ValueError。"""
        self.assertTrue(await CommunicationService.is_conversation_participant(
            self.db_a, self.cid, self.alice_id))
        await set_account_active(self.db_a, self.alice_id, False)
        # 成员资格不受停用影响（撤的是账号层，不是成员层）
        self.assertTrue(await CommunicationService.is_conversation_participant(
            self.db_a, self.cid, self.alice_id))
        decision = await ConversationPolicy.authorize(
            self.db_a, self.cid, self.alice_id, layer='inbound')
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, REASON_ACCOUNT_INVALID)
        with self.assertRaisesRegex(ValueError, '账号不可用'):
            await CommunicationService.send_message(
                self.db_a, self.cid, self.alice_id, 'blocked', client_message_id='k1')
        self.assertEqual(await self.db_a.messages.count_documents({}), 0)
        # 恢复启用后立即放行（撤权不留持久残留）
        await set_account_active(self.db_a, self.alice_id, True)
        result = await CommunicationService.send_message(
            self.db_a, self.cid, self.alice_id, 'ok', client_message_id='k2')
        self.assertEqual(await self.db_a.messages.count_documents({}), 1)
        self.assertEqual(result['content'], 'ok')

    async def test_concurrent_first_writes_from_two_processes_deduplicated(self):
        """两个独立客户端（模拟两进程）并发同键首写：唯一索引拦截，恰好一封。"""
        results = await asyncio.gather(
            CommunicationService.send_message(
                self.db_a, self.cid, self.alice_id, 'once', client_message_id='race-key'),
            CommunicationService.send_message(
                self.db_b, self.cid, self.alice_id, 'once', client_message_id='race-key'),
        )
        self.assertEqual(len({item['id'] for item in results}), 1)
        self.assertEqual(await self.db_a.messages.count_documents({}), 1)
        self.assertEqual(await self.db_a.notifications.count_documents({}), 1)


class RevocationRaceWindowDocumentationTests(ReplicaCase):
    """已知缺陷固化（按要求记录现状、不做大改）：

    send_message 的授权（ConversationPolicy.authorize）→ 落库（insert_one）
    段不在事务内、插入前无二次账号复核——授权通过后的并发停用不回滚写入。
    若未来按 WS02 事务化（run_transaction 包裹授权+插入），本用例会失败，
    届时须随实现更新为"写入被拒"的语义断言。
    """

    async def test_write_lands_when_account_disabled_between_authorize_and_insert(self):
        original_insert = AsyncIOMotorCollection.insert_one
        reached, proceed = asyncio.Event(), asyncio.Event()
        paused = False

        async def intercept(collection, document, **kwargs):
            nonlocal paused
            if (not paused and collection.name == 'messages'
                    and document.get('conversation_id') == self.cid):
                paused = True
                reached.set()
                await asyncio.wait_for(proceed.wait(), 5)
            return await original_insert(collection, document, **kwargs)

        with patch.object(AsyncIOMotorCollection, 'insert_one', intercept):
            task = asyncio.create_task(CommunicationService.send_message(
                self.db_a, self.cid, self.alice_id, 'raced'))
            await asyncio.wait_for(reached.wait(), 5)
            # 插入已越过授权点：此刻并发停用（模拟后台目录管理操作）
            await self.db_b.users.update_one(
                {'_id': ObjectId(self.alice_id)}, {'$set': {'is_active': False}})
            proceed.set()
            result = await asyncio.wait_for(task, 10)

        # 现状：写入照常落库，离线通知副作用照常产生（撤权对下一条消息才生效）
        self.assertEqual(result['content'], 'raced')
        self.assertEqual(await self.db_a.messages.count_documents({}), 1)
        self.assertEqual(await self.db_a.notifications.count_documents({}), 1)
        # 撤权对下一条消息立即生效（逐条实时查库确认存在）
        with self.assertRaisesRegex(ValueError, '账号不可用'):
            await CommunicationService.send_message(
                self.db_a, self.cid, self.alice_id, 'blocked')
        self.assertEqual(await self.db_a.messages.count_documents({}), 1)


# ---------------------------------------------------------------------------
# 场景 2：多 worker 分发（bus 模式 + 两个独立客户端模拟两进程）
# ---------------------------------------------------------------------------

class CrossWorkerDistributionTests(ReplicaCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        mode_patch = patch.object(settings, 'EVENT_BUS_MODE', 'bus')
        mode_patch.start()
        self.addCleanup(mode_patch.stop)
        reset_bus()
        self.addCleanup(reset_bus)
        # 进程 A：写侧发布者（ws_events 走 client_a）；进程 B：独立客户端读侧
        configure_bus(self.db_a, worker_id='worker-a')
        await ensure_ws_collections(self.db_a)

    async def test_message_and_notification_reach_other_process_via_event_bus(self):
        manager_a = get_connection_manager()
        ws_alice_a = FakeManagerSocket()
        await manager_a.connect_to_chat(ws_alice_a, self.alice_id, self.cid, 'a1')

        manager_b = ConnectionManager()
        ws_bob_b = FakeManagerSocket()
        ws_bob_notif_b = FakeManagerSocket()
        await manager_b.connect_to_chat(ws_bob_b, self.bob_id, self.cid, 'b1')
        await manager_b.connect_to_notifications(ws_bob_notif_b, self.bob_id, 'b2')

        reader_a = EventBusReader(make_manager_deliverer(manager_a), self.db_a)
        reader_b = EventBusReader(make_manager_deliverer(manager_b), self.db_b)
        task_a = asyncio.create_task(reader_a.run())
        task_b = asyncio.create_task(reader_b.run())
        try:
            await asyncio.sleep(0.2)  # 读侧任务就绪（首游标从最老存活事件起）
            result = await CommunicationService.send_message(
                self.db_a, self.cid, self.alice_id, '跨进程 hello')
            await self._wait_for(lambda: ws_bob_notif_b.sent)
        finally:
            await self._cancel(task_a, task_b)

        # 已知缺陷（高，随报告）：server_seq 是 ObjectId 12 字节大端整数（约
        # 2^92），超出 BSON int64 上限——bus 模式下携带 server_seq 的聊天帧发布
        # 必然失败（"MongoDB can only handle up to 8-byte ints"），send_chat_message
        # 捕获后退回本进程直投。跨 worker 的实时消息分发实际失效，且被回退掩盖。
        # 此处固化现状：消息帧不经总线跨进程投递（bob 的连接收不到 message 帧，
        # 仅可能收到不带 server_seq 的 notification_count 计数帧）。
        self.assertEqual([f['type'] for f in ws_bob_b.sent if f['type'] == 'message'], [])
        self.assertEqual([f['type'] for f in ws_alice_a.sent], ['message'])

        # 通知帧/未读数帧不带 server_seq：正常经总线跨进程投递
        # （未读计数字帧按现有实现投递 active_connections，bob 的聊天与通知
        # 连接都在册，两侧各收到一份计数字）
        (notif_frame,) = [f for f in ws_bob_notif_b.sent if f['type'] == 'notification']

        # 跨进程可见性：B 进程客户端能读到 A 进程写入的消息与通知文档
        message_doc = await self.db_b.messages.find_one({'conversation_id': self.cid})
        self.assertEqual(message_doc['content'], '跨进程 hello')
        self.assertEqual(message_doc['_id'], ObjectId(result['id']))
        notifications = await NotificationService.get_notifications(self.db_b, self.bob_id)
        self.assertEqual(len(notifications), 1)
        self.assertEqual(notifications[0]['title'], '新消息')
        self.assertEqual(notif_frame['data']['id'], notifications[0]['id'])

        # 总线帧时序：notification/personal 正常发布（chat 帧发布失败不落总线）；
        # 同一事件流内 _id 单调，notification 先于 personal
        frames = await self.db_b[WS_EVENTS_COLLECTION].find({}).sort('_id', 1).to_list(10)
        kinds = [frame['kind'] for frame in frames]
        self.assertEqual(kinds, ['notification', 'personal'])


# ---------------------------------------------------------------------------
# 场景 5：通知送达语义（离线写入 → 重连取未读 + 在册连接实时推送）
# ---------------------------------------------------------------------------

class NotificationDeliveryTests(EndpointHarness, ReplicaCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.build_app()
        mode_patch = patch.object(settings, 'EVENT_BUS_MODE', 'local')
        mode_patch.start()
        self.addCleanup(mode_patch.stop)

    async def create_message_notification(self):
        return await NotificationService.create_notification(
            db=self.db_a, title='新消息', content='hello',
            sender_id=self.alice_id, sender_name='Alice', sender_role='doctor',
            recipient_id=self.bob_id, notification_type='message')

    async def test_offline_notification_surfaces_on_reconnect_and_pull(self):
        """离线期间写入的通知：重连即得未读数初始帧；REST 拉取同一事实源。"""
        notif_id = await self.create_message_notification()
        await asyncio.sleep(0.1)  # 让实时推送任务落空（此刻无任何连接）
        # B 进程客户端读到同一通知文档（跨进程可见）
        self.assertEqual(await NotificationService.get_unread_count(self.db_b, self.bob_id), 1)
        pulled = await NotificationService.get_notifications(self.db_b, self.bob_id)
        self.assertEqual([item['id'] for item in pulled], [notif_id])

        self.start_identity(unified=False)
        self.ws_user_id = self.bob_id
        ws = FakeWebSocket()
        task = asyncio.create_task(self.notif_endpoint(ws, self.db_a))
        try:
            first = await self.next_frame(ws, 'notification_count')
            self.assertEqual(first, {'type': 'notification_count', 'count': 1})
        finally:
            await self._cancel(task)
        # 已读后重连：初始未读数归零
        await NotificationService.mark_all_as_read(self.db_a, self.bob_id)
        ws = FakeWebSocket()
        task = asyncio.create_task(self.notif_endpoint(ws, self.db_a))
        try:
            second = await self.next_frame(ws, 'notification_count')
            self.assertEqual(second, {'type': 'notification_count', 'count': 0})
        finally:
            await self._cancel(task)

    async def test_connected_notification_socket_receives_live_push(self):
        """在册通知连接：通知写入后实时收到帧（id 与落库文档一致）。"""
        ws = FakeManagerSocket()
        manager = get_connection_manager()
        await manager.connect_to_notifications(ws, self.bob_id, 'n1')
        notif_id = await self.create_message_notification()
        await self._wait_for(lambda: ws.sent)
        (frame,) = ws.sent
        self.assertEqual(frame['type'], 'notification')
        self.assertEqual(frame['data']['id'], notif_id)
        # 现有实现语义：未读计数字帧只投递 active_connections（聊天连接），
        # 通知连接不收到计数字更新（观察项，随报告记录，不做行为改动）
        self.assertEqual([item['type'] for item in ws.sent], ['notification'])


if __name__ == '__main__':
    unittest.main()
