# WP5-WS04 多 worker WebSocket 广播：设计决策稿

- 日期：2026-11-07
- 范围：只做代码/配置/文档调研与设计写作，不修改任何代码；本仓库（medicalassistant / Rehabman）后端为主，前端仅涉及影响面引用。
- 依据：`docs/development-plan-2026-11-07.md:196`（WS04 完成标准："跨worker消息、过期/撤权、broker故障和慢消费者可验证"）；`docs/wp5-ws01-message-structure-inventory-2026-11-07.md:164`（D11 决策点：Redis pub/sub vs Mongo change streams，本文为其决议输入）；`backend/app/api/websockets.py:132-135`（WS01 轮留下的 WS04 待办注释）。
- 结论先行：本地 Mongo 大概率为 standalone 单节点（证据见 §4.1），change streams 前提大概率不成立 → **推荐方案 A2（Mongo capped collection + tailable cursor 事件总线）**，零新依赖、standalone 可用；A1（change streams）保留为 Mongo 转 replica set 后的升级位；B（Redis）需用户明确授权才考虑。

---

## 一、现状盘点（影响面清单）

### 1.1 ConnectionManager：进程内存单例

`backend/app/api/websockets.py:19-136`。三张连接表全部是进程内字典：

| 结构 | 位置 | 内容 |
|---|---|---|
| `active_connections` | websockets.py:22 | `user_id -> {connection_id -> WebSocket}` |
| `chat_rooms` | websockets.py:24 | `conversation_id -> {user_id -> {connection_id -> WebSocket}}` |
| `notification_connections` | websockets.py:26 | `user_id -> {connection_id -> WebSocket}` |

模块级实例化并留有 WS04 待办注释：websockets.py:131-136

> 多 worker 限制（WS04 待办）：ConnectionManager 为进程内存单例，多 uvicorn worker 部署时各进程各持一份连接表，跨 worker 的聊天室广播与在线判定会失效（离线判定也只对本进程准确）。

推送 API 全部只遍历本进程字典：`send_personal_message`（:84-91）、`send_chat_message`（:93-101）、`send_notification`（:103-113）、`broadcast`（:115-123，**全仓库无调用方，死 API**）、`get_active_users_in_chat`（:125-129）。

### 1.2 多 worker 影响面逐项

| # | 影响点 | 代码证据 | 多 worker 下的表现 |
|---|---|---|---|
| I1 | 聊天房间广播 | websockets.py:93-101；调用点 communication_service.py:366（send_message 广播）、:455（单条已读回执）、:504（会话已读回执）、:544（消息删除/撤回） | 发送者所在 worker 与收件人所在 worker 不同时，收件人连接不在本进程 `chat_rooms` → 消息已落库但实时帧静默丢失（前端刷新才可见） |
| I2 | 在线判定 → 离线通知误建 | communication_service.py:375（`get_active_users_in_chat` 判收件人是否在线）→ :382 建离线通知 | 收件人实际在线但连在另一 worker → 本进程判定"离线"→ **误建"新消息"通知**（收件人明明在线） |
| I3 | 通知推送 `/ws/notifications` | websockets.py:301-346；notification_service.py:167（`create_task(send_notification(...))`） | 通知在 worker1 落库、recipient 的通知 WS 连在 worker2 → 实时推送静默丢失（落库成功，仅"不实时"） |
| I4 | 未读数实时推送 | notification_service.py:171-177、:259-266（`send_personal_message` 推 `notification_count`） | 同 I3，跨 worker 丢失 |
| I5 | 房间出席事件（user_joined/user_left/typing） | websockets.py:178-188、:276-290、:249-259；`active_users` 列表来自本进程 `chat_rooms`（:125-129） | 事件广播只达同进程连接；`active_users` 名单跨 worker 不完整 → 前端在线名单错误 |
| I6 | 全局 broadcast | websockets.py:115-123 | 死 API，无调用方；若未来启用则"广播"只覆盖本进程 |
| I7 | 批量通知 | notification_service.py:184-268（`create_batch_notifications`） | 注释已声明无调用方（:199-201），但实现存在同样的跨 worker 失效 |

通知创建触发点全量盘点（决定总线必须覆盖的集合）：全仓库 `NotificationService.create_notification` 仅 3 处调用，全部在 communication_service.py——**:208（新会话建立）**、**:382（离线消息）**、**:569（消息撤回）**；`notification_router.py` 只有读/已读/删除入口，无创建入口。批量版无调用方。即：**业务侧唯一的事件源集合是 `messages`（间接）与 `notifications`（直接）**。

### 1.3 部署现状：当前是单 worker

`scripts/runtime.py:317-318` 启动后端：

```python
child, record = spawn("backend", [python, "-m", "uvicorn", "app.main:app",
    "--host", host, "--port", str(backend_port)], ROOT / "backend", env, ROOT / "logs")
```

**没有 `--workers` 参数 → 单进程单 worker**。因此 §1.2 的失效模式当前全部为"潜伏"而非"激活"——这正是 WS04 的设计前提：先显式化这个隐含约束（§5 S0），再决定是否/如何支持多 worker。

其他部署事实：

- 端口/环境变量机制：`MEDICALASSISTANT_HOST`（默认 127.0.0.1）、`MEDICALASSISTANT_BACKEND_PORT`（默认 5502）、`MEDICALASSISTANT_FRONTEND_PORT`（默认 5501），runtime.py:284-299；运行令牌与进程组身份管理 runtime.py:29-31、:121-136。
- runtime.py 职责边界明确："Never manages MongoDB or packages"（runtime.py:2）——Mongo 由外部生命周期管理，repo 内**没有任何 docker-compose / Dockerfile / rs.initiate 脚本**（`deploy/` 下仅有 nginx）。
- 应用启动序列：`main.py:119-131`——`connect_to_mongodb()`（:124）→ `setup_websockets(app)`（:127）→ `ensure_communication_indexes(mongodb_state.db)`（:131，幂等 create_index，`backend/app/db/indexes.py:24`）。**WS04 的事件总线 worker 与 capped collection 初始化可挂在同一启动序列**。

### 1.4 依赖与中间件现状

- `backend/requirements.txt`：fastapi 0.104.1、uvicorn 0.24.0、websockets 12.0、motor 3.2.0、pymongo[srv] 4.6.0。**无 redis 客户端**。
- `core/config.py:118-121` 存在 `REDIS_HOST/REDIS_PORT/REDIS_PASSWORD/REDIS_DB` 配置项，但 `core/cache.py:14-25` 是纯内存 `Cache` 实现，全文无 `import redis`——**Redis 配置是遗留摆设，无任何使用方**。引入 Redis 等于引入一个全新故障域，不是"启用既有设施"。
- Mongo 连接：`config.py:30` 默认 `mongodb://localhost:27017`，URL 无 `replicaSet` 参数；连接池参数 :33-38。
- 项目约束：医疗合成数据环境、尽量少引入基础设施（任务书），与 1.3 的"独立生命周期、最小部署"基调一致（`docs/baseline-2026-11-07.md:27`）。

---

## 二、多 worker 失效模式汇总

| 场景 | 单 worker（现状） | 多 worker（若直接加 `--workers N`） |
|---|---|---|
| 聊天实时消息帧 | 正常（收发双方必在同进程） | I1：跨 worker 静默丢帧，落库成功但收件人无感知 |
| 离线通知判定 | 准确 | I2：误建通知（在线判为离线）；**不会漏建**（真离线时判定仍为离线），失效方向单一 |
| 通知实时推送 | 正常 | I3/I4：跨 worker 静默丢失 |
| 房间在线名单 | 准确 | I5：名单不完整、typing 不可见 |
| 断线重连 | 客户端重连回任意 worker 均可 | 重连分散后 I1—I5 随机复现（与连接分布相关，难复现、难测试） |

设计含义：I2 的失效方向是"误建"而非"漏建"，属于可用性缺陷而非数据丢失；I1/I3/I5 是实时性缺陷，落库与离线同步（`sync_offline_messages`）仍兜底数据不丢。因此多 worker 化的收益是"实时性正确"，不是"数据正确"——这为方案 C（单 worker WS）保留了合理性空间。

---

## 三、方案对比

统一对照维度：机制 / 新增依赖 / 延迟 / 可靠性 / 改动量 / 失败模式。

### 方案 A1：Mongo Change Streams

- **机制**：每个 worker 在启动序列（main.py:119-131 处）起一个 asyncio 任务 `db.watch([...])`（motor 3.2.0 原生支持），监听 `messages` / `notifications` 的 `insert` 事件；事件直接携带落库文档，worker 过滤后投递给本进程连接。写路径零改动——`send_message` / `create_notification` 照常落库，分发完全是读侧。
- **新增依赖**：无。
- **延迟**：本地单节点 replica set 下毫秒级。
- **可靠性**：resume token 断点续传；但 token 需持久化，且超出 oplog 窗口后无法恢复（只能回退"从当前时刻开始"，接受一个丢失窗口）。
- **改动量**：小（新增 bus 模块 + 启动任务；ConnectionManager 的 send_* 方法语义收窄为"本进程投递"）。
- **失败模式**：**硬前提是 replica set**——standalone 直接报错 `The $changeStream stage is only supported on replica sets`（MongoDB 官方约束，change streams 依赖 oplog）。§4.1 的证据链表明本仓库大概率是 standalone → 此方案大概率**开箱即不可用**。另外瞬态事件（typing/user_joined/user_left，不落业务库）没有天然载体，需另行解决。

### 方案 A2：Mongo capped collection + tailable cursor（Mongo 自建事件总线）

- **机制**：新建 `ws_events` capped collection（如 1MB），写侧对每个"需要实时分发的事件"显式 `insert_one` 一条事件帧（含 `ev_v` schema 版本、事件类型、目标 user_id/room、载荷）；每个 worker 启动时开 tailable await cursor（pymongo `cursor_type=TAILABLE_AWAIT` + `max_await_time_ms`，motor 支持），收到事件后**只投递给本进程命中目标的连接**。每个 worker 都收到全部事件 → 天然 fan-out，按目标过滤本进程命中即可，无需去重（不同 worker 投递的是各自的本地连接）。
- **新增依赖**：无。
- **延迟**：await cursor 毫秒级（`max_await_time_ms` 控制唤醒粒度）。
- **可靠性**：事件在 capped 窗口内可按 `_id` 回放——worker 断线重连时从上次 `_id` 续读，短暂断线的消息可补；超过窗口被覆盖则丢（聊天域有落库 + 离线同步兜底，可容忍）。无独立 broker 进程，故障域就是 Mongo 本身（Mongo 挂了整个应用本来就挂）。
- **改动量**：中。比 A1 多一处写（写侧显式 publish），但换来两个 A1 没有的能力：① **standalone 可用**；② 瞬态事件（typing/user_joined/user_left）可以只写 `ws_events` 不写业务库，天然解决 I5。
- **失败模式**：消费者慢 → cursor 落后到 collection 回卷时 Mongo 会 kill cursor，需检测死亡并按 last `_id` 重连重放 → 重放产生**重复事件**，去重依赖客户端幂等（WS03 已建 `client_message_id` + `message_ack` 幂等骨架，websockets.py:203、:244，方向一致）；capped collection 一经创建不能改容量，需容量评估（§5 S1）。

### 方案 B：Redis Pub/Sub

- **机制**：发布事件帧到 channel（如 `ws:room:{conversation_id}`、`ws:user:{user_id}`），各 worker 订阅并投递本进程连接。
- **新增依赖**：`redis`（redis-py ≥5 自带 asyncio 支持）客户端 + **一个常驻 Redis 服务器进程**（新基础设施组件）。
- **延迟**：亚毫秒，四案中最低。
- **可靠性**：pub/sub 是 fire-and-forget——订阅断线期间的 publish **直接丢失、无回放**，可靠性弱于 A2；需自建重连与（如需）补偿。
- **改动量**：中（bus 模块 + 配置启用）。config.py:118-121 的 REDIS_* 配置可复用，但如 §1.4 所述，这不是"启用既有设施"而是全新引入。
- **失败模式**：新增独立故障域（Redis 宕机 → 全部实时推送失效，且与 Mongo 故障域不重合，监控/运维面扩大）；与项目"尽量少引入基础设施"约束冲突。**必须由用户决策授权**（§7 决策点 1）。

### 方案 C：粘性会话 / 单 worker WS（部署侧约束）

先澄清一个常见误区：**"WS 单独拆一个进程（C2）并不能消除跨进程分发需求"**——REST 进程里 `send_message` 落库后触发的广播（communication_service.py:366）依然要跨进程送到 WS 进程，问题只是从"N 个 worker"缩小为"REST 池 + WS 进程"两类，总线照旧需要。真正规避总线的形式只有一种：

- **机制（C1）**：显式固定"WS 服务 = 单 worker"。现状 runtime.py:317 实际已是单 worker，C1 的全部内容是**把这个隐含约束显式化**：runtime 启动参数固定、启动时校验、文档标注"多 worker 扩容受 WS04 方案门控"。
- **新增依赖**：无。
- **延迟**：零（无中间环节）。
- **可靠性**：无新故障域；单点风险 = worker 进程挂 → 全部 WS 断开，客户端重连即可恢复（websockets 12.0 + 前端已有重连 hook，`frontend/src/hooks/useWebSocket.ts:60-90`）。uvicorn 单进程 asyncio 可承载数千级 WS 连接，对医疗合成数据环境绰绰有余。
- **改动量**：最小（几行护栏 + 文档）。
- **失败模式**：连接数天花板（单进程）；无法按 development-plan-2026-11-07.md:196 的 WS04 完成标准验收"broker 故障和慢消费者"——**没有 broker 就没有这两项可验证性**，只能以"无 broker 架构"重构验收口径，或作为 A2 落地前的过渡口径（§7 决策点 5）。

### 方案 D：前端轮询退化（列出不推荐）

REST 定时拉取替代推送。延迟秒级、服务器压力随客户端数线性增长、与 WS04"跨worker消息可验证"目标相悖；且前端已有 WS 资产（useWebSocket hook、NotificationPusher）。仅作为极端降级路径记录，不进入推荐序列。

### 对比表

| 维度 | A1 Change Streams | A2 Capped+Tailable | B Redis Pub/Sub | C1 单 worker WS | D 轮询 |
|---|---|---|---|---|---|
| 新增 pip 依赖 | 无 | 无 | redis | 无 | 无 |
| 新增基础设施 | **需 Mongo 转 replica set** | 无 | Redis 服务器 | 无 | 无 |
| standalone Mongo 可用 | **否** | **是** | 是 | 是 | 是 |
| 实时分发延迟 | ~ms | ~ms | 亚 ms | 0（无分发） | 秒级 |
| 断线补传 | resume token（oplog 窗口内） | 按 `_id` 回放（capped 窗口内） | 无（fire-and-forget） | — | — |
| 瞬态事件（typing/出席） | 需另找载体 | 天然支持（只写 ws_events） | 支持 | 本进程内即正确 | — |
| 写路径改动 | 零 | 显式 publish 事件帧 | 显式 publish 事件帧 | 零 | 零 |
| 改动量 | 小 | 中 | 中 | 极小 | — |
| broker 故障/慢消费者可验证（WS04 标准） | 可 | 可 | 可 | **不可（无 broker）** | — |
| 主要风险 | 前提大概率不成立 | cursor 回卷重复、容量固定 | 新故障域、需用户授权 | 无法满足验收口径 | 体验/负载劣化 |

---

## 四、推荐与前提核验

### 4.1 关键前提核验：本地 Mongo 是不是 standalone？

**结论：所有可得证据指向 standalone 单节点，且写作时无法活体确认（Mongo 未运行），按 standalone 口径设计。**

证据链：

1. `config.py:30`：默认连接串 `mongodb://localhost:27017`，无 `replicaSet` 参数——若部署为副本集，URL 必须携带该参数才能生效。
2. `docs/isolated-demo-accounts.md:7`：合成数据工具"拒绝……远程地址、DNS/SRV、凭证、URI参数**或副本集种子列表**"，:14 示例连接串为 `mongodb://127.0.0.1:37020`——项目自建的 Mongo 实例明确是单机直连形态。
3. `docs/first-integration-pilot.md:47`：试点容器 `rehab-pilot-mongo` 联调后已 `docker rm` 连库销毁；`docs/baseline-2026-11-07.md:27,33`：数据库"由独立生命周期管理"、用隔离测试容器验证——repo 内不存在任何副本集初始化脚本（全文检索 `replSet|rs.initiate|replicaSet` 无命中，仅测试文件一处无关命中）。
4. `runtime.py:2`：启动器"Never manages MongoDB"——没有任何自动化流程会去改造 Mongo 拓扑。
5. 活体核验受阻：写作时 `localhost:27017` 连接拒绝（服务未运行），无法执行 `db.hello()` 确认 `setName`/`msg` 字段。**S0 切片包含一条必须执行的核验命令**（§5），若核验结果为"已是单节点 replica set"，推荐按 §4.3 的条件分支反转回 A1。

### 4.2 推荐：A2（capped collection 事件总线）为目标，C1 为前置显式化

理由：

1. **前提核验反转了默认倾向**：任务书预设"无新依赖通常倾向 A（change streams）"，但 A1 在 standalone 上开箱即不可用（§3 A1），A2 同为零新依赖却不需要 replica set——在"尽量少引入基础设施"约束下 A2 是唯一同时满足"零依赖 + standalone 可用 + 可满足 WS04 验收口径"的方案。
2. **瞬态事件有家**：typing / user_joined / user_left 不落业务库，A1 下没有载体；A2 下它们只是 `ws_events` 里的一类事件帧，I5 一并闭环。
3. **失败域不扩大**：总线就是 Mongo，不新增进程、不新增监控对象（对比 B）。
4. **升级位保留**：一旦未来 Mongo 转为 replica set，A2 的读侧投递逻辑不变，写侧事件帧可平滑换成 `watch()` 窃取（或干脆双轨过渡），A2 的 `ws_events` schema 设计（`ev_v` 版本字段）即为此预留。
5. **C1 先行、成本近零**：现状本就是单 worker（runtime.py:317），先显式化护栏把"隐性依赖"变成"显性约束"，再实施 A2；即使 A2 延期，系统行为也与今天完全一致，零回退成本。

不推荐 B 作为默认：新故障域 + 新运维面 + fire-and-forget 可靠性反而低于 A2，除非用户明确授权（§7 决策点 1）。

### 4.3 条件分支（S0 核验结果驱动）

| S0 核验结果 | 走向 |
|---|---|
| standalone（预期） | 按 §5 主线实施 A2 |
| 已是单节点 replica set | A1 变为首选（写路径零改动、无 capped 容量问题）；A2 降为备选 |
| 用户接受引入 Redis | B 重新进入比选（延迟与生态成熟度占优），但 A2 仍以"无新基础设施"胜出 |

---

## 五、迁移步骤（分切片，每片可独立提交/验收/回退）

### S0 部署事实显式化 + Mongo 拓扑核验（无行为变化）

- 执行拓扑核验（只读）：
  ```python
  # backend/.venv/bin/python -I
  from pymongo import MongoClient
  h = MongoClient('mongodb://localhost:27017', serverSelectionTimeoutMS=4000).admin.command('hello')
  print(h.get('setName'), h.get('msg'))   # 均为 None → standalone；setName 存在 → replica set
  ```
- runtime.py / 文档显式标注当前单 worker 约束（C1 护栏：如启动参数固定 + 注释说明多 worker 受 WS04 门控）。
- 验收：拓扑结论落档（本文档更新）；单 worker 约束在启动器可见。
- 回退：无（纯文档/注释）。

### S1 事件总线读侧：`ws_events` capped collection + tailable cursor 任务

- `db/indexes.py` 增加幂等初始化：检查 `ws_events` 不存在则 `create_collection(size=..., capped=True)`（capped 集合一经创建不可改容量，容量按"峰值事件速率 × 回放窗口"评估，医疗合成数据规模下 1MB 起步偏保守）。
- 新增 `EventBus` 模块：读侧 tailable await cursor（`cursor_type=TAILABLE_AWAIT`、`max_await_time_ms`），事件帧 `{ev_v: 1, kind, target: {user_id|conversation_id}, payload, ts}`；cursor 死亡检测 + 按 last `_id` 重连重放。
- 挂入 main.py 启动序列（:119-131 现有 startup hook 位置），每个 worker 一个读任务。
- 本阶段写侧不动（仍直连 manager）——读侧事件尚无人发布，纯增量、零行为变化。
- 验收：双 uvicorn 进程（模拟多 worker）手工 insert 事件帧，两进程均能收到并路由到各自本地连接。
- 回退：删启动任务即可。

### S2 写侧切换：三类推送改走总线

- 覆盖点（= §1.2 影响面的写入口）：聊天房间帧（communication_service.py:366、:455、:504、:544）、通知推送与未读数（notification_service.py:167、:171-177、:256、:259-266）。
- 加配置开关 `EVENT_BUS_MODE: local | bus`（config.py 既有 env 风格）：`bus` 模式下写侧 publish 到 `ws_events`，`local` 模式保持现状直连——**回滚开关就位后才允许删直连路径**。
- ConnectionManager 的 `send_*` 方法语义收窄为"本进程投递"（读侧任务复用它们）；顺带处置死 API `broadcast()`（websockets.py:115-123，无调用方，删除或注释声明本进程语义）。
- 验收：双进程环境下，worker A 发消息 → worker B 上的收件人收到实时帧；`EVENT_BUS_MODE=local` 回退后行为与主线前一致。
- 回退：开关切回 `local`。

### S3 在线判定与出席事件跨 worker 化（I2/I5）

- 在线判定：新增 presence 存储代替本进程 `get_active_users_in_chat`——`ws_presence` 集合（user_id、worker_id、心跳时间），TTL 索引（时长数值待定，§7 决策点 3）自动清理失联 presence；communication_service.py:375 改查 presence。
- 出席/瞬态事件：typing / user_joined / user_left（websockets.py:178-188、:249-259、:276-290）改为 publish 到 `ws_events`（不落业务库），`active_users` 名单改由 presence 集合聚合。
- 验收：双进程下，A 进程在线用户不会被 B 进程的发送方误判离线（I2 消除）；两端出席名单一致（I5 消除）。
- 回退：presence 查询处保留 `local` 分支（退回本进程判定，失效模式与今天相同）。

### S4 可靠性验证（对齐 WS04 完成标准）

- development-plan-2026-11-07.md:196 的三项可验证性：跨 worker 消息（S2 验收覆盖）、broker 故障（停/重启 Mongo → cursor 重连重放、`EVENT_BUS_MODE=local` 兜底演练）、慢消费者（人工暂停消费进程 → capped 回卷 → 重复事件被 WS03 幂等骨架去重，websockets.py:203、:244）。
- 过期/撤权断连属于 WS02 范畴，本稿不展开。
- 验收：三项留证（日志 + 测试），失败项如实保留失败状态（开发计划验收原则）。

### S5（条件升级位）Mongo 转 replica set 后切 change streams

- 仅当 §7 决策点 2 被批准时启动：写侧事件帧替换为 `watch()`，读侧投递逻辑与 `ev_v` schema 不变。

---

## 六、风险与回滚

| 风险 | 影响 | 缓解 | 回滚 |
|---|---|---|---|
| S0 拓扑核验结果与预期相反（已是 replica set） | 推荐反转为 A1，A2 工作量部分沉没 | S1 的 EventBus 抽象层对两种读侧通用 | 切换读侧实现即可 |
| capped 容量不足 → 事件被覆盖、重放窗口缩水 | 断线 worker 补传丢事件 | 容量按峰值×窗口评估并留余量；聊天域落库+离线同步兜底 | 扩容需新建集合并切名（capped 不可原地改），迁移脚本预备 |
| cursor 回卷 → 重复事件 | 前端重复帧 | WS03 幂等键 + message_ack 去重；事件帧带 `_id` 供客户端去重 | — |
| presence 心跳误判（worker GC 暂停超过 TTL） | 在线误判离线 → 重复通知（与今天多 worker 失效同向，非新缺陷类别） | TTL 时长 ≥ 心跳间隔 × 3；心跳写失败不阻塞主流程 | S3 回退 `local` 分支 |
| 总线写放大（每事件一次 insert） | Mongo 写入量上升 | 医疗合成数据规模下可忽略；S4 压测留证 | 开关切 `local` |
| 双轨期（S1/S2）事件重复投递 | 同一帧收到两次 | 双轨仅存在于开关灰度窗口，读侧按 `kind + _id` 去重 | — |
| 整体回退 | — | 全链路可回退单 worker 现状：开关 `local` + 删启动任务 + drop `ws_events`/`ws_presence`（均无业务数据，可随时销毁） | 数据零迁移，无回滚负债 |

---

## 七、需要用户决策的点

| # | 决策点 | 选项与建议 | 默认 |
|---|---|---|---|
| 1 | 是否允许引入 Redis（方案 B） | 建议否：新故障域 + fire-and-forget 可靠性低于 A2 + 违背"少引入基础设施"约束；仅当未来出现超高事件吞吐或已有 Redis 运维能力时重新评估 | 不引入 |
| 2 | 是否接受把本地 Mongo 转单节点 replica set（解锁 A1） | 需改 mongod 启动参数（`--replSet`）+ `rs.initiate`，改变部署形态、引入 oplog 磁盘开销；收益是写路径零改动。建议：不转，走 A2；转则推荐反转为 A1 | 不转 |
| 3 | presence TTL / 心跳间隔数值（S3） | 建议 TTL 90s、心跳 30s（3 倍冗余）；影响离线通知误判窗口 | 待确认数值 |
| 4 | 瞬态事件（typing/user_joined/user_left）是否要求跨 worker 一致 | 若否，S3 范围缩减为仅 presence 判定，I5 接受为本进程语义 | 建议要求（成本低，S3 已覆盖） |
| 5 | WS04 验收口径：C1 过渡期是否允许先行部分验收 | A2 落地前，"broker 故障/慢消费者"两项无法验证；建议允许 C1 作为"架构声明"先行验收，S4 完成后闭合 | 建议允许，待确认 |
| 6 | `ws_events` 容量与保留策略 | 建议起步 1MB（约数千条事件帧）；有量级预期后调整 | 待确认 |

---

## 附：本稿未覆盖 / 待核实清单

- Mongo 活体拓扑（S0 核验命令，写作时服务未运行无法确认）。
- `ws_events` 事件帧 schema 细节（与 WS01 已冻结的信封 `{type, data, message_id, server_seq, ts}` 的映射，见 wp5-ws01 盘点 D7/D11）——建议在 S1 实施前出契约补充。
- WS02 的连接期撤权复核（WS04 完成标准中的"过期/撤权"项）与 presence 机制的耦合，留待 WS02 设计稿。
- `frontend/vite.config.pilot.ts`（未跟踪文件）是否影响试点期 WS 路由，未纳入本稿。
