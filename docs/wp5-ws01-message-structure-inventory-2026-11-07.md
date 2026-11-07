# WP5-WS01：历史会话/消息两套结构盘点与统一契约前置分析

- 日期：2026-11-07
- 范围：只做代码与文档盘点，不修改任何代码；本仓库（medicalassistant / Rehabman）后端 + 前端。
- 依据：`docs/development-plan-2026-11-07.md:196-200`（WS01—WS05）、`docs/baseline-2026-11-07.md:35`（HTTP/WS 握手已统一令牌校验；WS 会话成员、消息持久化、多 worker、连接中撤权尚未闭环）。
- 本文不含任何真实聊天内容，所有引用均为代码结构证据。

---

## ① 两套结构盘点（集合 / 字段 / 读写方）

### 1.1 总览：实际上"两套 schema + 一个内存广播层 + 两处桩接口"

| # | 结构 | 载体 | 集合 | 现状 |
|---|------|------|------|------|
| A | 模型类 `Message` / `Conversation` | `backend/app/models/communication.py:10-185` | `messages` / `conversations` | 仅有 CRUD 封装，**无任何路由/服务调用**（死代码） |
| B | `CommunicationService` 隐式 schema | `backend/app/services/communication_service.py` | 同上两个集合 | 唯一实际挂载生效的 HTTP 通信 API |
| C | WebSocket 内存广播层 | `backend/app/api/websockets.py` | 不落库 | 进程内存单例，`type=="message"` 分支不持久化 |
| D | 角色路由桩 | `doctor_router.py` / `patient_router.py` | 无 | 返回硬编码空值 |
| E | 通知体系（相邻域） | `Notification` + `notifications` 集合 | `notifications` | 与聊天 WS 通知耦合，非聊天消息 |

### 1.2 结构 A：模型类（participants 数组 + is_group，支持群聊）

定义于 `backend/app/models/communication.py`：

- **Message**（communication.py:10-80），`collection_name = "messages"`（:12）。字段：`conversation_id`、`sender_id`、`sender_type`（patient/doctor/health_manager/system，:18）、`content`、`content_type`（text/image/file，:20）、`attachments`（`[{file_name, file_type, file_url, file_size, uploaded_at}]`，:70-79）、**`is_read` / `read_at`**（:22-23）、`created_at/updated_at`（`datetime.utcnow()`，:37-38）、`metadata`。
- **Conversation**（communication.py:83-185），`collection_name = "conversations"`（:85）。字段：`title`、**`participants` 数组 `[{user_id, user_type, joined_at}]`**（:90, :135-143）、`last_message`（内嵌摘要，:153-162）、**`unread_counts`（按 user_id 的字典，存在会话文档内）**（:92, :164-168）、**`is_group`**（:93）、`creator_id`、`status`（active/archived/deleted，:95）、`metadata`。

**读写方**：仅 `MessageCRUD` / `ConversationCRUD`（`backend/app/db/crud_services.py:359-422`），经 `get_crud_services`（crud_services.py:442-443）与 `get_message_crud` / `get_conversation_crud`（`backend/app/core/dependencies.py:94-100`）暴露。**全仓库检索没有任何 router/service 依赖这两个 getter**（grep `get_message_crud|get_conversation_crud` 仅命中定义处）——结构 A 目前是死代码。注意 `doctor_router.py:6` 直接 import 了 `PatientCRUD, DoctorCRUD`，说明 crud_services 体系整体仍在用，只有消息/会话部分空转。

单聊/群聊区分：`is_group` 标志 + participants 数组长度（crud_services.py:400-414，单聊查询 `$size == len(user_ids)` 且 `is_group: False`）。

### 1.3 结构 B：`CommunicationService` 隐式 schema（participant1/2 固定双人，实际生效）

挂载：`backend/app/main.py:211`，`app.include_router(communication_router, prefix="/api")` → `/api/communications/*`（路由定义 `backend/app/api/routers/communication_router.py`）。

- **conversations 文档**（communication_service.py:145-155）：`_id`、**`participant1_id` / `participant2_id`**、`type`（默认 `"chat"`）、`status`（"active"）、`created_at`、`last_message_time`、`last_message_preview`、`metadata`。**无 `is_group`，无双人数组 → 只支持单聊**。建会话按双 participant 有序/无序对去重（:127-142），但**无数据库唯一索引**，并发创建可产生重复会话。
- **messages 文档**（communication_service.py:227-239）：`conversation_id`（字符串形式 ObjectId）、`sender_id`、**`recipient_id`**、`content`、**`type`**、**`timestamp`（`datetime.now()` 本地时区，:226）**、**`read` / `read_at`**、**`deleted` / `deleted_at`（软删除，:442-445）**、`attachments`（List[Dict] 直接透传，无上传端点）、`metadata`。

**读/写方与关键行为**：

- 读会话列表/详情：`get_conversations`（:22-70，按 `participant1_id/participant2_id` $or 查询）、`get_conversation`（:73-116，参与者校验 :85）。
- 读消息：`get_messages`（:161-204）——**读取时有副作用：把对方发的未读消息直接置 `read=true`（:196-202）**；分页用 `before_id` + `timestamp` 比较（:176-180）。
- 写消息：`send_message`（:207-308）——参与者校验（:218-220）→ 落库 → 更新会话 `last_message_*`（:245-253）→ 尝试经 WS 广播（:271-282）→ 收件人不在线则建 Notification（:284-304）。
- 已读：`mark_message_as_read`（仅 recipient 可标，:339-376）、`mark_conversation_as_read`（:379-425）。
- 删除：`delete_message` 仅允许**发送者**软删（:428-465），收件人无"删除"语义。
- 离线同步：`sync_offline_messages`（:468-511），按 `recipient_id + timestamp > last_sync_time`。
- 未读数：从 messages 集合 count（`read=False & deleted=False & recipient_id=me`，:311-336）——与结构 A 的 `unread_counts` 会话内嵌字段是**两套未读语义**。

已知缺陷证据：
- `mark_conversation_as_read` 的已读回执回查（:398-403）用 `read_at >= datetime.now().replace(microsecond=0)`，而 update_many 刚把 `read_at` 设为更早的 `now()`，该近似查询大概率查不到刚标记的消息 → 回执推送通常为空。
- 全仓库无 `messages`/`conversations` 的 `create_index` 调用（grep 无结果）→ 关键查询路径无索引，`conversation_id` 均以字符串存取。

### 1.4 结构 C：WebSocket 层（不落库的广播 + 内存成员表）

`backend/app/api/websockets.py`，由 `main.py:118` `setup_websockets(app)` 注册：

- **`/ws/chat/{conversation_id}`**（websockets.py:135）：
  - 握手鉴权走 `get_current_user_ws`（`backend/app/core/auth.py:84-116`：query 参数 `token` 优先，其次 cookie；校验有效期/类型/账号启用——与 baseline 记录一致）。
  - **入房不校验该 user 是否为 conversation 参与者**（websockets.py:140-155 直接 `connect_to_chat`），任何人持有效令牌可进任意 conversation_id 房间收发。
  - `type=="message"` 分支**不写库**（:178-195，原文注释"这里可以添加数据库更新代码"），广播的 message `id` 用 `datetime.now().timestamp()`（:187）→ 刷新后 id 变化、无幂等、无历史。
  - `type=="read_receipt"` 分支也不更新数据库（:207-222，注释占位）。
  - `typing` 状态广播（:196-206）。
- **`/ws/notifications`**（websockets.py:248-293）：推未读通知数（:270-274），入站消息不处理。
- **ConnectionManager 为模块级内存单例**（:18-131）：`active_connections` / `chat_rooms` / `notification_connections` 全部进程内字典（:131）→ 多 uvicorn worker 下跨进程不可见（直接阻塞 WS04）。
- 连接生命周期内无授权复核：令牌过期、账号停用、被移出会话均不会断连（无任何定时/事件校验）。

### 1.5 结构 D：角色路由桩（另一处"消息"同名入口）

- `backend/app/api/routers/doctor_router.py:227-247`：`GET /communications` 返回 `[]`（:236）、`POST /communications` 返回 `{"id": "new_message_id"}`（:247），仅角色判断，不接任何 service。
- `backend/app/api/routers/patient_router.py:231-248`：同样为桩（:237 返回 `[]`，:248 返回 `{"id": "new_message_id"}`）。

### 1.6 相邻域：通知与 Agent 对话（避免盘点遗漏）

- **Notification**（models/communication.py:188-220，Pydantic 模型）+ `notifications` 集合（`notification_service.py:37` 起）：通知是聊天外溢出的提醒通道（send_message 离线时创建，communication_service.py:292-304），`recipient_id` 单接收者，无会话概念。与聊天契约需划清边界但不必合并。
- **Agent/LLM 对话**（`agent_service.py:123-131` 等）：LLM 请求报文，不持久化为聊天消息，不属于 WS01 域。
- **死代码 `app/api/api.py`**：import `chat`、`auth`、`users` 等端点模块（api.py:7-11），但 `backend/app/api/endpoints/` 下只有 `agent_optimized.py / db_optimizer.py / prediction.py` 三个文件，`chat.py` **不存在**；且 `main.py` 全文未引用 `api_router`。即 api.py 一旦被 import 即 ModuleNotFoundError，是未挂载的死代码——**前端 `chatService.ts` 预期的 `/chat/*` 后端实现从未存在过**。

### 1.7 两套结构字段对照（同集合、异 schema）

| 维度 | 结构 A（模型类） | 结构 B（CommunicationService） |
|---|---|---|
| 会话成员 | `participants: [{user_id,user_type,joined_at}]` | `participant1_id` / `participant2_id` |
| 群聊 | `is_group` 支持 | 不支持 |
| 未读 | 会话内嵌 `unread_counts{user_id}` | messages 按 `read=False` count |
| 已读字段名 | `is_read` / `read_at` | `read` / `read_at` |
| 时间 | `created_at`（utcnow） | `timestamp`（`datetime.now()` 本地时区） |
| 删除 | 无删除语义 | `deleted` / `deleted_at` 软删，仅发送者 |
| 附件 | `attachments[{file_name,file_type,file_url,file_size,uploaded_at}]` | `attachments` List[Dict] 透传（无 schema 约束） |
| 状态 | active/archived/deleted | status 仅 "active"，无归档入口 |

> 待核实：生产/测试库中两个集合是否已同时存在 A、B 两种形态的文档（mock_data_scripts 下 15 个脚本均不创建 conversations/messages，grep 无命中；库内实际数据量与形态需 mongosh 只读统计确认）。

---

## ② 前端消费面与模拟点

| 文件 | 现状 | 证据 |
|---|---|---|
| `frontend/src/pages/Patient/Communication.tsx` | **纯本地 mock**：消息为组件内硬编码 state（:23-27），发送只 push 本地数组（:31-44），医生信息硬编码（:47-53），不调用任何 API。路由 `routes.tsx:348` | Communication.tsx:20 区块注释"模拟消息数据" |
| `frontend/src/pages/Doctor/Communication.tsx` | **纯本地 mock**（:20 起硬编码消息），路由 `routes.tsx:303`、`:327`（医生/健康管理师两个布局各挂一份） | 不发任何网络请求 |
| `frontend/src/services/chatService.ts` | 面向 `/chat/*` 的完整客户端（conversations/messages/read/offline/unread/search，:38-172），**但后端不存在 `/api/chat` 路由（见 1.6），全部调用必然 404** | chatService.ts:42、53、79 等 |
| `frontend/src/components/Patient/ChatComponent.tsx` | 功能最全的聊天组件（HTTP 拉历史 :586、WS :193-227、IndexedDB 离线缓存 :32-38/358-544、pendingMessages 重试队列 :141-151、消息 status: sent/delivered/read/error/pending :40-52），**但全仓库无任何页面 import 它，当前为死代码** | grep `ChatComponent` 仅命中自身与 routes 无关文件 |
| `frontend/src/hooks/useWebSocket.ts` | 原生 WebSocket + 自动重连（3s×10，:60-90）；**连接不附加任何凭据**（:49 `new WebSocket(url)` 裸建连，依赖 cookie） | 无 token 参数拼接 |
| `frontend/src/components/common/NotificationPusher.tsx` | WS 地址 `${VITE_WS_URL}/notifications/ws`（:25）= `/medical/ws/notifications/ws`，与后端 `/ws/notifications` **路径不匹配** → 通知推送实际不通 | NotificationPusher.tsx:25 vs websockets.py:248 |
| WS URL 前缀 | `frontend/.env.local:5` `VITE_WS_URL=/medical/ws`，注释即"后端路由为 /ws/chat/{conversation_id}"；ChatComponent 拼 `/medical/ws/chat/{id}`（ChatComponent.tsx:193-195）路径正确，依赖部署层剥离 `/medical` 前缀。vite dev 代理只转发 `/api` 且 ws:true（vite.config.ts:29-45），dev 下 `/medical/ws` 是否可达**待核实**（nginx 配置不在仓库内）。 | — |

**结论**：前端目前没有任何一条真实可用的聊天链路——两个通信页面是硬编码 mock，唯一写完的 ChatComponent 未被挂载，chatService 指向不存在的后端，通知 WS 路径错位。这反而降低了 WS05 的兼容负担：前端可以按新契约直接实现，无需迁就旧的 `/chat/*` 路径（但 chatService/ChatComponent 中的既有交互设计可作需求参考）。

---

## ③ 现状 vs WS01—WS05 完成标准差距

| 任务 | 完成标准（development-plan-2026-11-07.md:196-200） | 现状 | 差距定性 |
|---|---|---|---|
| WS01 | 不丢历史或既有功能；明确真实对话成员、中心及诊疗授权 | 两套 schema 已盘点（本文①）；群聊仅存在于死代码结构 A；附件无上传/存储实现；无 center/诊疗授权字段 | **本文即交付物**；契约冻结待做 |
| WS02 | 握手、入站及出站验证有效账号、会话参与和授权；撤权/过期按确认时限断连 | 握手已统一（auth.py:84-116，baseline:35）；HTTP 收发有参与者校验（communication_service.py:85/171/219）；**WS 入房无成员校验**（websockets.py:140-155）；连接期无授权复核/断连 | ConversationPolicy 缺失，必须新建 |
| WS03 | 数据库失败不返回成功或广播；重试不重复消息；受权离线追溯 | HTTP 路径落库但**无幂等键**（send_message 无客户端消息 ID，重发即重复）；**WS 消息完全不落库**（websockets.py:178-195）且广播 id 用时间戳；无 ACK 机制；read_receipt 不写库；离线同步已有（:468-511）但仅限结构 B 双人文档 | 持久化与幂等必须统一到单一 service |
| WS04 | 跨 worker 消息、过期/撤权、broker 故障和慢消费者可验证 | ConnectionManager 进程内存单例（websockets.py:131），无 broker、无慢消费者策略 | 全部待建 |
| WS05 | 真实医患授权测试发送、历史、去重、已读、断网与撤权；不将长期 token 放 URL | 前端聊天页全 mock/死代码（见②）；token 未入 URL（好），但依赖 cookie 的部署前提取决于跨站拓扑（identity-integration-contract.md:117 的原则可沿用） | 前端按新契约实现即可，无旧协议包袱 |

**现状可保留的部分**：
- `get_current_user_ws` 握手校验（auth.py:84-116）——已按 baseline 验证，直接复用。
- 结构 B 的 service 行为骨架（参与者校验、软删、离线同步、未读 count、离线建通知），可在统一 schema 上改造而非重写。
- `communication_router` 的 REST 路径形状（conversations/messages/read/sync）可作为对外契约基础，仅调整字段与幂等。
- 前端 ChatComponent 的交互资产（IndexedDB 模型、重试队列、status 生命周期）作为 WS05 实现参考。

**必须迁移/重做的部分**：
- conversations 集合：`participant1_id/participant2_id` → 统一 `participants` 数组（或双写过渡），补 `is_group`、成员角色、（待业务确认）`center_id`/诊疗关联。
- messages 集合：`read` vs `is_read` 二选一；`timestamp`（本地时区）→ 统一 UTC；补 `client_message_id` 幂等键、`server_seq`/排序键。
- WS 消息路径：从"广播即成功"改为"先持久化、再带 ACK 广播"，复用 `CommunicationService.send_message`。
- ConnectionManager：进程内单例 → 跨 worker 分发（WS04）。
- 死代码清理：`models/communication.py` 的 A 版模型与 crud_services 中 Message/Conversation CRUD 二选一保留；`app/api/api.py`（引用不存在的 chat 端点）需删除或修正；doctor/patient `/communications` 桩要么接真实现要么下线。

---

## ④ 迁移风险与统一契约决策点

### 4.1 数据迁移风险

1. **同集合双 schema 并存**：`messages`/`conversations` 中若同时存在 A 形态（`is_read`、participants 数组、`unread_counts`、`is_group`）与 B 形态（`read`、`recipient_id`）文档，按"字段存在性"判别是唯一可靠的分流依据；判错方向会静默丢字段（如把 A 文档的 participants 当缺失处理）。→ 迁移前必须先做只读统计（见⑤第 2 步），此项数据量为**待核实**。
2. **时区混用**：B 的 `timestamp`/`read_at`/`last_message_time` 用 `datetime.now()`（服务器本地时区），A 用 `datetime.utcnow()`。若服务器时区变化或迁移时统一为 UTC，历史消息排序会漂移；`get_messages` 的 `before_id` 分页以 `timestamp` 精确比较（communication_service.py:176-180），时区处理不当会导致漏页/重页。
3. **读取即置已读的副作用**（:196-202）：迁移脚本或回填工具若复用 `get_messages`，会把大量历史消息误标已读。迁移期间应冻结该副作用或改用只读查询。
4. **未读双轨**：`conversations.unread_counts`（A，内嵌计数）与 messages count（B，实时算）并存，切换时前端未读角标可能出现跳变；需定一个权威来源后废弃另一个。
5. **重复数据**：conversations 按"双 participant 对 + type"应用层去重（:127-142）且无唯一索引，历史库中可能已有重复会话；合并时若不先做会话级去重，同一对用户会出现双会话、消息分裂。
6. **conversation_id 类型**：B 全程字符串化 ObjectId（:158 返回 str，消息内存 str），若统一契约改用 ObjectId 或引入 `conversation_key`，需全量回写 messages.conversation_id，量级大时需分批。
7. **前端本地缓存**：ChatComponent 已定义 IndexedDB `chat-messages-db` v1（ChatComponent.tsx:358-386），契约字段变化后旧缓存会造成本地重复/错位，需升版本号强制重建。
8. **桩接口行为变化**：doctor/patient `/communications` 桩从未返回真实数据，接入真实实现后若有旧客户端调用，响应形状变化需在 WS05 端到端里显式覆盖。

### 4.2 统一契约必须冻结的决策点（WS01 交付核心）

| # | 决策点 | 备选与建议 | 待业务/安全确认 |
|---|---|---|---|
| D1 | 会话成员模型 | 建议：`participants: [{user_id, role, joined_at}]` 数组 + `is_group` + `group_meta`（标题/管理员），保留 `participant1_id/participant2_id` 兼容读一版后废弃 | 群聊本期是否落地（结构 A 有模型无业务）；会话是否必须绑定诊疗关系（医患授权 AUTH03/AUTH04） |
| D2 | 中心与诊疗授权字段 | 会话文档是否带 `center_id` / `encounter_ref`（诊疗关联），决定 MC02 多中心隔离能否直接套用 | 中心归属、跨中心会诊是否进入 WS 域 |
| D3 | ConversationPolicy（WS02） | 入房/入站/出站三层校验同一规则：有效账号 + 会话参与者 + 授权版本匹配；连接期定时复核（时限数值待安全确认），撤权/过期按确认时限断连 | 断连时限；撤销粒度（单会话 vs 全局） |
| D4 | 幂等键 | `client_message_id`（客户端 UUID）+ `(sender_id, client_message_id)` 唯一索引；HTTP 与 WS 入站同键；重放返回既有消息 + 相同 ACK | ID 生成端（客户端 vs 服务端短 ID） |
| D5 | 已读语义 | per-recipient `read/read_at`（沿用 B）还是 per-message `read_by[]`（群聊必需）；已读回执以服务端落库为准，废弃"读取即已读"副作用 | 群聊已读回执量级 |
| D6 | 删除语义 | 发送者撤回（对所有人隐藏，`deleted=true`）+ 接收者本地删除（per-user 隐藏）两层，是否都要本期实现 | 产品语义 |
| D7 | WS 事件信封 | 统一 `{type, data, message_id, server_seq, ts}`；`message / ack / read_receipt / typing / user_joined / user_left / error` 枚举冻结；错误码表（可沿用 wp1 契约的错误码风格） | server_seq 生成方式（单集合自增 vs ObjectId 排序） |
| D8 | 附件 | 冻结上传端点 + 存储介质（本地卷 vs 对象存储，**待定**）+ 类型/大小白名单 + `attachments` 元数据 schema（沿用 A 的 file_name/file_type/file_url/file_size/uploaded_at 为基础） | 存储选型与合规（病历相关附件驻留要求，关联 MC01） |
| D9 | 连接凭据 | 维持 token 不入 URL（现状未违反 WS05）；短期连接凭据（一次性 ticket 换 WS 升级）与 cookie 方案二选一，需与部署拓扑（`/medical` 前缀、跨站）联调确认 | 部署层反代配置（不在仓库内，待核实） |
| D10 | 通知边界 | 消息通知（notifications 集合）与聊天消息分离，仅保留"离线→通知"桥（communication_service.py:284-304 模式） | — |
| D11 | 多 worker 分发（WS04 依赖 WS01 冻结的事件信封） | Redis pub/sub vs Mongo change streams，影响事件信封是否需携带路由元数据 | 运维选型 |

---

## ⑤ WS01 交付建议：契约草案章节结构 + 实施顺序

### 5.1 统一契约草案建议章节（`docs/` 下新建，建议名 `communication-contract-draft-2026-11-07.md`）

1. **范围与非目标**：医患/健康管理者会话域；排除 notifications 域与 Agent LLM 对话（引用 1.6）。
2. **统一数据模型**：Conversation / Message / Attachment 字段表、必填性、时区约定（UTC）、schema_version；A/B 字段映射表（含 1.7 对照）。
3. **会话成员与单聊/群聊规则**：participants 结构、单聊去重键、群聊预留、成员增删事件。
4. **ConversationPolicy**：三层校验矩阵（握手/入站/出站）、诊疗与中心授权前置条件、连接期复核与断连时限。
5. **REST 契约**：以 `/api/communications/*` 现有形状为基（conversations / messages / read / sync / unread-count），补幂等头、错误码、分页游标。
6. **WS 契约**：事件信封、消息类型枚举、ACK 与重试语义、read_receipt、错误码；明确"不落库不广播"。
7. **幂等与去重**：client_message_id、唯一索引、重放响应。
8. **已读/删除语义**（D5/D6 决议）。
9. **附件契约**（D8 决议）。
10. **迁移方案**：双 schema 识别规则、批次、回滚开关、迁移前后只读统计口径。
11. **多 worker 分发前提**（D11，仅冻结信封，不含实现）。
12. **开放问题清单**：所有"待核实/待业务确认"项集中登记。

### 5.2 实施顺序建议（每步可独立验收、可回退）

1. **WS01-a 冻结契约**：按 5.1 出草案，评审后冻结 D1—D11（本盘点可直接作为第 2、10 章素材）。
2. **WS01-b 数据摸底（只读）**：对 `messages`/`conversations` 做只读统计——A/B 形态文档数、时间字段时区分布、conversation_id 类型、疑似重复会话、总量与增速；产出迁移规模结论（消除本文"待核实"项）。**不改数据。**
3. **WS03-前置 幂等与持久化统一**：`send_message` 加 `client_message_id` 唯一索引；WS `message` 分支改为调用同一 service 落库后再广播（先持久化后广播即满足"数据库失败不广播"）；广播携带服务端 message_id。此步不动 schema 主体，风险最低、收益最大。
4. **WS01-c schema 迁移**：按摸底结果执行 participants 数组迁移 + UTC 统一 + 已读字段归一（含双写或视图兼容期），配合唯一索引（单聊去重、幂等键）；保留回滚开关。
5. **WS02 ConversationPolicy**：WS 入房成员校验、入站/出站校验复用同一策略对象、连接期定时授权复核与断连时限；同时清理"读取即已读"副作用，已读走显式接口。
6. **WS04 多 worker 分发**：按 D11 冻结的信封接入 broker/change stream，替换内存单例 ConnectionManager；验证跨 worker、慢消费者、broker 故障。
7. **WS05 前端**：基于新契约实现通信页（可复用 ChatComponent 资产并升级 IndexedDB 版本），修正 NotificationPusher WS 路径，下线或接真 doctor/patient `/communications` 桩，删除 `app/api/api.py` 死代码；端到端覆盖发送/历史/去重/已读/断网/撤权，并用短期凭据完成"token 不入 URL"验证。
8. **验收对账**：对照 WS01—WS05 完成标准逐条留证（迁移前后统计、撤权断连时限实测、多 worker 压测），失败项如实保留失败状态（与开发计划验收原则一致）。

---

## 附：本次盘点未覆盖 / 待核实清单

- 生产/测试库中两集合的实际文档量与双 schema 并存情况（需只读查询，见⑤第 2 步）。
- 部署层 `/medical` 前缀反代与 WS 升级配置（nginx 配置不在仓库内）；vite dev 代理是否覆盖 `/medical/ws`。
- 群聊是否为本期业务范围（结构 A 有模型、无任何业务调用）。
- 附件存储介质选型与合规要求（当前后端无任何上传端点，`UploadFile/multipart` 仅出现在邮件代码 report_scheduler_service.py:11）。
- `frontend/vite.config.pilot.ts`（未跟踪文件）是否引入了试点专用通信配置，未纳入本次盘点范围。
