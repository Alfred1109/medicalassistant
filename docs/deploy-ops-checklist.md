# 部署运维检查单（T54 整合稿）

> **声明：本检查单整合自本地开发环境的验证结论，未经生产部署验证。**
> 所有条目均注明出处文档/代码；标注「已验证」的指在本机隔离/开发实例上
> 实测通过，标注「未实机验证」的为文档建议值或未在生产量级执行过的流程。
> RPO/RTO/保留期等数字均为建议值，须经业务确认后才有约束力
> （`docs/backup-restore-plan.md` §0/§5）。

---

## 一、首次部署

### 1. MongoDB：nofile ulimit 必须配置（红线级）

- **要点**：数据卷内孤儿 `.wt` 文件堆积 + 容器默认 `nofile=1024` 会导致
  mongod 文件描述符耗尽 crash-loop（`epoll: Too many open files`）。
  2026-11-14 演练时 rehab_rs 容器即因该组合崩溃循环，数据卷内曾堆积约
  4.2 万个孤儿 `.wt` 文件（`docs/backup-restore-plan.md` §7.2 坑 4）。
  `deploy/mongodb/compose.yml` 已为 mongo 服务加
  `ulimits.nofile: soft/hard 65536`（教训注释在文件头部）。
- **出处**：`deploy/mongodb/compose.yml:6-12`；`docs/backup-restore-plan.md` §7.2；
  `docs/development-plan-2026-11-07.md` §14（临时实例曾因句柄上限不足退出，
  目标部署应结合负载核验资源限制）。
- **验证命令**：
  ```bash
  # 应输出 65536（本机已验证，2026-11-15 运行中容器实测）
  docker compose -f deploy/mongodb/compose.yml exec -T mongo sh -c 'ulimit -n'
  ```
- **注意**：65536 是针对当前开发数据量级的取值；正式部署负载更高，须结合
  实际负载复核（§14 提醒，未实机验证）。

### 2. MongoDB：副本集初始化与事务能力验收

- **要点**：单节点副本集 `rehab_rs` 提供多文档事务能力，**不提供高可用**；
  `ping` 成功只证明可连接，不证明事务能力，必须核对 `hello()` 并跑真实
  副本集上的事务测试（`deploy/mongodb/README.md`）。
- **验证命令**：
  ```bash
  # 必须同时看到 setName: 'rehab_rs' 和 isWritablePrimary: true（本机已验证）
  docker compose -f deploy/mongodb/compose.yml exec -T mongo mongosh --quiet --eval 'db.hello()'
  ```
  ```bash
  # 随访事务测试（仅限新建、仅含合成数据的本地实例；每用例独立 rehab_txn_ 随机库）
  # 缺 REHAB_TEST_REPLICA_URI 时明确跳过——普通内存测试通过不能替代这些结果。
  cd backend
  DEBUG=false REHAB_TEST_REPLICA_URI='mongodb://127.0.0.1:37021/?replicaSet=rehab_rs&directConnection=true' \
    .venv/bin/python -m pytest tests/test_followup_transactions_mongo.py -q
  ```
- **出处**：`deploy/mongodb/README.md`（隔离验证记录 2026-11-08：事务提交、
  回滚、主节点选举、启停流程均实测；`directConnection=true` 仅适用本机
  映射端口，跨机器部署不可复用该 URI）。
- **网络边界**：宿主端口绑定 `127.0.0.1`；`mongod --bind_ip_all` 仍监听容器
  网络，同一 Docker 网络中的容器可**无认证**访问，不能把回环端口发布视为
  完整网络隔离。正式部署需另行配置账号、网络隔离、备份和副本集成员
  （`deploy/mongodb/README.md` 头部声明）。

### 3. 应用密钥：SECRET_KEY 必须显式提供

- **要点**：`SECRET_KEY` 未在环境显式提供时**每次启动随机生成**
  （`backend/app/core/config.py:116`）。恢复后不还原同一 `SECRET_KEY` 会使
  全部已签发 token 失效——属「可恢复但强制全员重新登录」的软失败，应纳入
  环境备份避免（`docs/backup-restore-plan.md` §1.3）。
- **验证**：核对部署环境变量清单中 `SECRET_KEY` 为显式固定值（未实机验证，
  属部署层人工流程）。

### 4. 源端（康复问卷管理系统）：TRUSTED_PROXY_HOPS 反代必须配置

- **要点**：反代部署必须配置 `TRUSTED_PROXY_HOPS`（单层 Nginx 边缘设 1）。
  默认 0 会忽略 `X-Forwarded-Proto`，反代后集成面
  `POST /integration/v1/fill-sessions` 的 create/launch 会因「非 HTTPS」
  全部被拒（400 `secure_transport_required`）
  （源端 `.env.example` TRUSTED_PROXY_HOPS 段注释，实测来源；
  `docs/security/production-baseline.md` §密钥和环境接口：模板只有一层
  可信 Nginx，设 `TRUSTED_PROXY_HOPS=1`，Nginx 用 `$remote_addr` 覆盖
  客户端提交的 XFF，不要把跳数任意调大，引入 CDN/LB 须重新确认）。
- **出处**：源端 `/mnt/acer-ssd/multiproject/康复问卷管理系统/.env.example:16-22`；
  源端 `docs/security/production-baseline.md:30`；实现
  `app/utils/client_ip.py`（按显式配置跳数解析，异常回退 remote_addr）。
- **验证**：反代就位后实际调用一次集成面 create/launch，确认非 400
  `secure_transport_required`（未实机验证）；并验证客户端伪造 XFF/Proto
  不影响审计来源（源端 baseline 部署验收项）。

### 5. 源端：集成限流依赖 workers=1

- **要点**：`IntegrationRateLimiter`（源端 `app/services/integration_grant_service.py`）
  计数保存在**进程内存**，依赖 Gunicorn `workers = 1` 前提；多 worker 时各
  进程独立计数，实际放行配额按进程数放大。调大 worker 前必须先迁移共享
  存储（如 Redis）。限流键为集成客户端凭证身份（非 IP），只覆盖填报会话
  与共享申请的写路径端点，超限 429 `rate_limited` + `Retry-After`
  （源端 `docs/security/production-baseline.md:12`；`.env.example:27-31`
  `INTEGRATION_RATE_LIMIT_PER_MINUTE` / `INTEGRATION_RATE_LIMIT_WINDOW_SECONDS`）。
- **验证**：核对源端 systemd/启动配置 Gunicorn 为 1 进程 8 线程
  （`production-baseline.md:11`；未实机验证）。

### 6. 填报（表单集成）默认关闭

- **要点**：跨系统填报入口**保持默认关闭**。启用前提（尚开放项）：真实
  HTTPS 与跨站 Cookie 浏览器验收、outbox/API04 事件推送、撤权恢复类授权
  代际边界、历史 URL 盘点迁移等；本地隔离验证不能代替线上授权或临床验收
  （`docs/embed-credential-contract-gap.md:51`；
  `docs/development-plan-2026-11-07.md` §14 多处「填报保持默认关闭」记录）。
- **验证**：部署后核对填报入口处于关闭状态（人工核对，未实机验证）。

### 7. 患者域：canonical 未启用是当前默认态

- **要点**：canonical 模式未启用、迁移未生产执行、cutover CLI 禁用
  （`backend/app/patients/README.md:41-43`）。全新部署的
  `patient_domain_state` 缺省语义为 legacy 默认域
  （`backend/app/patients/repository.py:38-62`）。切换按
  `docs/patient-domain-cutover-plan.md` 波次执行，见下文「版本升级与迁移」。
- **出处**：`docs/patient-domain-cutover-plan.md` §6 草案声明。

---

## 二、日常运行

### 1. 全库备份由应用外调度器执行（架构约束）

- **要点**：Mongo 全库备份（`backend/scripts/backup_mongodb.py`）必须由
  **应用之外的调度器**（systemd timer / cron）周期执行，不依赖 FastAPI
  进程存活——恢复场景往往发生在应用已不可用时。应用内 `BackupSchedule`
  只承担受限业务 JSON 导出（`restorable: false`），不承担恢复职责，两者
  并存、不复用执行通道（`docs/backup-restore-plan.md` §0/§3）。
- **备份形态**：`mongodump --gzip --archive=<单文件> --oplog`（副本集特性，
  备份窗口内有写入时必须带 `--oplog`）；同目录产出
  `rehab-mongodb-<UTC时间戳>.manifest.json`（SHA256、掩码 URI、各库各集合
  计数与索引清单、`patient_domain_state` 存在性与 mode）。
- **调度频率建议（RPO）**：≤ 24h 每日全量；高频写入期可收紧至 ≤ 1h；
  备份窗口选低峰（`docs/backup-restore-plan.md` §2.1，建议值待业务确认）。
- **告警红线**：备份失败需可见，不能静默失败——现有 `backup_schedule`
  的 except-日志模式即静默失败反例（`docs/backup-restore-plan.md` §6）。
- **验证命令**（单次手工备份，本机 2026-11-14 演练已验证；本机无
  mongodump 二进制，经 docker 包装执行）：
  ```sh
  docker run --rm --network host -v /tmp:/tmp --entrypoint mongodump \
      mongo:7.0.16 mongodump --uri <uri> --gzip --archive=<路径> --oplog
  # 经 backup_mongodb.py 接入：
  .venv/bin/python -m scripts.backup_mongodb --uri <rehab_rs> --oplog \
      --output-dir <目录> --mongodump <wrapper脚本>
  ```
- **踩坑**：mongo 镜像 entrypoint 会强制降权（uid 999），`docker run mongo:7.0.16 mongodump ...`
  对宿主属主目录无写权限，必须 `--entrypoint mongodump` 绕过；挂载路径
  容器内≠宿主路径，wrapper 统一挂 `/tmp:/tmp`（`docs/backup-restore-plan.md` §7.2）。

### 2. 保留策略（GFS 梯度，建议值）

- 每日 7 份 / 每周 4 份 / 每月 6 份；患者域迁移等不可逆变更前的手工档
  **保留至该变更稳定运行满 1 个月**。
- 存放要求：备份目录权限收紧（属主只读）；archive 与业务 JSON 导出
  （含患者明文）、媒体目录（原始患者材料）**同等加密存放**（age/gpg 公钥
  加密，私钥线下另管）；异地副本只增密文；manifest 与 archive 同级同权
  保管（`docs/backup-restore-plan.md` §2.2，未实机验证——加密与异地上传
  属脚本外人工流程，演练未覆盖）。

### 3. 应用内调度：多 worker 安全性现状

- **BackupSchedule（业务 JSON 导出）**：已按 T37（D1 修复）实现
  `find_one_and_update` 原子领取——到点条件放进 filter，只有领取成功的
  进程才执行导出，多 worker 不再重复落敏感文件（
  `backend/app/operations/runtime.py` `run_if_due` 注释；取舍：领取先于
  导出，导出中崩溃宁可漏一次）。
- **提醒扫描（followup reminders）**：多 worker 已安全——通知与投递台账
  （deliveries ledger）在同一事务内写入，`_id` 幂等，并发首跑经
  DuplicateKeyError 重读收敛，「没有无台账的 insert」（
  `backend/app/services/followup_reminder_service.py:140-161` 及
  `docs/wp5-ws04-multiworker-design-draft-2026-11-07.md`）。
- **report_scheduler 调度路径已删除**：`start()/stop()/_scheduler_loop()`
  属死代码已处置；若未来恢复后台报表调度，**必须先按 T37 同款原子领取
  重写扫描逻辑**（fire-then-update 无原子领取，启用即复刻多 worker 重复
  执行缺陷），再接入应用生命周期 + shutdown，并补多进程并发验证用例
  （`docs/t53-dead-code-disposal-report-scheduler.md`；执行链
  `_process_schedule` 等保留但不可达）。

### 4. 数据保留与日志

- `save_operations` 会按 `data_retention_days` 清理过期 `audit_logs` /
  `notifications`（`backend/app/operations/runtime.py`），调整保留天数前
  确认审计留存要求（源端 baseline 要求审计日志半年以上留存并由独立采集
  器外发——该要求针对源端，本项目可参照，未实机验证）。

---

## 三、版本升级与迁移

### 1. 不可逆变更前强制加备

- **要点**：对患者域迁移等高风险变更，**变更前强制手工加备一次**，使该
  操作的 RPO 趋近 0（`docs/backup-restore-plan.md` §2.1）；迁移命令本身
  无恢复函数，崩溃/未知提交结果先查证，**不回灌旧备份**需先查证
  （`backend/app/patients/README.md:74-78`）。

### 2. 患者域切换门槛（G1–G5，任一不满足不启动波次）

- 出处：`docs/patient-domain-cutover-plan.md` §1.2。**canonical 未启用、
  切换未经任何验收，本文档为草案。**
  - **G1 盘点干净**：真实库只读盘点 `backend/scripts/patient_reference_audit.py`，
    `ambiguous` 逐组人工核实并有书面处置结论（用法
    `docs/patient-reference-audit.md`）。
  - **G2 迁移演练**：`backend/scripts/manage_clinical_patients.py` 在隔离
    实例完成 inspect→apply→复查，manifest 比对一致（生产 apply 未执行）。
  - **G3 内核分派全绿**：`patient_access.py` 双模式 + fail-closed 测试全过。
  - **G4 备份可恢复**：完整备份 + **独立恢复演练**成功（业务 JSON 导出与
    迁移快照目录均不替代备份）。
  - **G5 维护窗口写者排除**：迁移窗口内应用写者、后台调度、外部直连工具
    均由**部署流程**排除（工具无法证明不存在未知外部 Mongo 写者）。
- **波次结构**：波次 0（门槛核验）→ 波次 1（授权内核与读取面）→
  波次 2–6（写路径/提醒/统计/集成/新患者创建），每波回滚方式为「域开关
  回拨」（见下文红线）。波次 1 启用前还有业务决策项（停用患者的统一 404
  口径）。

### 3. 显式回拨载体未落地前 canonical 不得启用

- **要点**：当前 `domain_mode` 对一切已存在但 `mode != canonical` 的状态
  文档 fail-closed 503（显式写 `mode: "legacy"` 也被拒绝），尚无「显式
  legacy」合法状态。生产启用 canonical 前必须先落地显式回拨载体（专用
  开关或受控显式 legacy 状态），否则 §5.1 的回拨 SOP 第 1 条不可执行
  （`docs/patient-domain-cutover-plan.md` §5.1 第 3 条）。

### 4. 标签唯一索引：盘点归零→维护窗口手工建，不进启动路径

- **要点**：**不得在未知数据上直接建唯一索引**。流程：
  1. 只读盘点（`backend/scripts/label_uniqueness_audit.py`），重复键组与
     异常形状计数**归零**才放行；
  2. 历史重复清理属业务决策，工具不代做；
  3. 维护窗口手工 `createIndex({name:1, category:1}, {unique:true, name:"uniq_tag_name_category"})`，
     **保持默认 binary collation**；不登记进 `app/db/indexes.py`，启动
     流程不改（`docs/tag-uniqueness-plan.md`）。
- **验证命令**（盘点；CLI 已在本机隔离临时库端到端验证，未触碰既有库）：
  ```bash
  cd backend
  MONGODB_AUDIT_URI="mongodb://localhost:27017" \
      .venv/bin/python -m scripts.label_uniqueness_audit > tag_audit.json
  ```
- 副本集演练测试 `tests/test_tag_uniqueness_replica.py` 由 `REHAB_TEST_TAGS_URI`
  门控，未提供 URI 自动跳过——不把默认跳过算作通过。

### 5. 副本集门控测试基线口径

- **要点**：副本集门控专项（e2e 演练 `REHAB_TEST_PATIENT_E2E_URI`、栅栏
  并发、调度多进程、迁移演练、跨系统闭环 `REHAB_TEST_CLOSED_LOOP=1`、
  随访事务 `REHAB_TEST_REPLICA_URI`、标签唯一性 `REHAB_TEST_TAGS_URI`）
  均显式 URI/环境变量门控，未配置时整体跳过；**不把默认跳过算作通过**。
  复跑基线参考：后端全量回归 `DEBUG=false` 767 passed / 277 skipped，
  前端 Node 测试 102 passed（`docs/development-plan-2026-11-07.md` §14）。
- **验证命令**（真实副本集事务测试，见上文「首次部署 §2」；其余专项按各
  文档的 URI 变量门控执行，均未在生产量级验证）。

### 6. 迁移演练记录与既有数据库接入边界

- 不可直接把其他实例的数据目录挂到本配置，也不可因需要事务而在应用中
  降级为非事务写入；既有数据库迁移应先核实拓扑和实际路径，在受控数据
  副本上演练备份恢复及兼容性，再安排停写、最终备份、迁移与业务验证
  （`deploy/mongodb/README.md`「既有数据库接入边界」）。

---

## 四、灾难恢复

### 1. 恢复唯一依据：mongodump 归档

- **要点**：业务 JSON 导出（`backend/app/operations/data_export.py`）标识
  `restorable: false`，只作业务层归档；恢复唯一依据是
  `mongodump --gzip --archive` 全量归档 + manifest，恢复质量由
  `backend/scripts/verify_restore.py` 对账（`docs/backup-restore-plan.md` §0）。

### 2. 恢复演练流程（隔离环境，季度一次；任何患者域迁移前必做一次）

- 出处与完整步骤：`docs/backup-restore-plan.md` §4；2026-11-14 本机隔离
  实例已完成首次实机闭环演练（§7），全链路已验证。
- 核心命令（本机演练实测）：
  ```bash
  # 隔离实例（独立容器，端口避开 37021，按 init-replica.js 同法初始化副本集）
  mongorestore --uri mongodb://127.0.0.1:<端口>/?replicaSet=<rs>&directConnection=true \
      --gzip --archive=<archive> --drop   # 带 --oplog 的归档加 --oplogReplay
  # 对账（退出码 0 才算通过）
  .venv/bin/python -m scripts.verify_restore --manifest <manifest> \
      --uri mongodb://127.0.0.1:<端口>/?replicaSet=<rs>
  ```
- 恢复后验证清单（§4 步骤 5）：集合计数对账、索引存在性（重点
  `clinical_patient_id_unique`、`patient_account_unique`、
  `uniq_conversation_sender_client_message_id`）、`patient_domain_state`
  存在性与 mode 一致（canonical 库恢复后必须仍是 canonical，否则
  `require_canonical` 拒绝服务）、业务冒烟（登录/患者列表/随访读写）、
  媒体目录条目数一致、记录用时对照 RTO。
- 负向用例已验证：篡改计数 → `count_mismatch`；删状态单例 → 同时报
  `count_mismatch` + `patient_domain_state_mismatch`（§7.4）。
- RTO 建议 ≤ 4h（含恢复+对账+冒烟）。本机演练实测恢复主链路 ~2.3s，
  **仅代表开发数据量级（~2 千文档），不推断生产 RTO**（§7.5）。

### 3. 已知对账「假差异」限制

- manifest 计数在 mongodump 结束**之后**经独立连接采集；备份窗口内有并发
  写入时对账可能出现假差异，根治属脚本增强项。低峰备份窗口下影响可忽略
  （`docs/backup-restore-plan.md` §6 / §7.6）。
- 脚本未覆盖（属人工流程）：媒体目录文件级同步（§1.2）、密钥保管（§1.3）、
  加密与异地上传；副本集扩为多节点后应把备份读偏好切到 secondary 并复核
  RPO（§5）。

### 4. 崩溃恢复与未知写者

- 迁移崩溃/未知提交结果先查证不回灌旧备份（`backend/app/patients/README.md:75-78`）；
  迁移工具不能证明不存在未知外部 Mongo 写者，须以部署流程（端口/进程/
  服务单元核查）兜底（cutover plan R12）。

---

## 五、已知限制与红线

| # | 红线/限制 | 依据 |
|---|---|---|
| 1 | **不得删除 `patient_domain_state` 文档**。删除会静默降级回 legacy：无 503、无告警，canonical 数据仍在但不再被消费，fail-closed 保障整体失效；回拨必须以显式域开关状态变更执行并留痕（变更单+复核人）。 | `docs/patient-domain-cutover-plan.md` §5.1；`backend/app/patients/repository.py:38-62` |
| 2 | **显式回拨载体落地前 canonical 不得启用**（显式 `mode:"legacy"` 当前也被 fail-closed 拒绝，无安全回拨路径）。 | 同上 §5.1 第 3 条 |
| 3 | **不得在未知数据上直接建唯一索引**（标签唯一索引须先盘点归零、维护窗口手工建，不进启动路径；§14 最初登记的缺口）。 | `docs/tag-uniqueness-plan.md`；`docs/development-plan-2026-11-07.md` §14 |
| 4 | **填报保持默认关闭**，启用前提未闭合前不得开启。 | `docs/embed-credential-contract-gap.md`；development plan §14 多处 |
| 5 | **业务 JSON 导出不是备份**（`restorable: false`，仍含患者信息、字段有限）；迁移工具快照目录也不替代备份。 | `docs/backup-restore-plan.md` §0；cutover plan G4 |
| 6 | **全库备份不得依赖 FastAPI 进程**——由应用外调度器执行；备份失败必须有告警，不得静默失败。 | `docs/backup-restore-plan.md` §3/§6 |
| 7 | **恢复 report_scheduler 调度前必须先加原子领取**（T37 范式），否则多 worker 重复执行；调度路径已删除，属死代码处置。 | `docs/t53-dead-code-disposal-report-scheduler.md` |
| 8 | **源端限流扩 worker 前必须先迁移共享存储**（Redis），当前进程内存计数仅 workers=1 成立。 | 源端 `docs/security/production-baseline.md:12` |
| 9 | **单节点副本集不提供高可用**，备份是唯一时间点回退手段；患者域迁移提交后不可逆，唯一回滚途径是全量归档恢复。 | `docs/backup-restore-plan.md` §1.1 |
| 10 | **Mongo 容器 nofile ulimit 不得移除**（孤儿 .wt 堆积 + 默认 1024 曾致 crash-loop）；不得直接挂载外部数据目录到本配置。 | `deploy/mongodb/compose.yml:6-12`；`deploy/mongodb/README.md` |
| 11 | **`users` 在 canonical 模式下只读**（唯一例外路径：波次 6 前的 people_import，切换前须冻结或豁免，见 R8）；迁移保留原 `users._id` 作患者主键。 | `backend/app/patients/README.md:20-21`；cutover plan R8 |
| 12 | **备份产物含患者数据的部分（业务 JSON 导出、媒体目录）必须加密存放**，绝不以明文离开生产主机；密钥与密文分地存放。 | `docs/backup-restore-plan.md` §2.2 |
| 13 | **副本集门控测试默认跳过不算通过**——须显式 URI 实跑。 | `docs/development-plan-2026-11-07.md` §14 |
| 14 | **canonical 窗口内写入不会自动回流 legacy**：回拨再启用会产生双侧数据分叉，重新启用前必须按 R9 对账清账。 | cutover plan §2 / §5.2 R9 |

---

## 附：验证状态汇总

- **本机已验证**：nofile=65536（运行中容器实测，2026-11-15）；副本集
  hello/事务/启停（2026-11-08 隔离验证）；备份→恢复→对账→负向用例闭环
  （2026-11-14）；标签盘点 CLI（隔离临时库）。
- **未实机验证**：RPO/RTO/保留期数值（业务未确认）；生产量级恢复耗时；
  加密与异地上传、媒体目录同步、密钥保管（人工流程，演练未覆盖）；
  systemd timer/cron 调度器落地；源端反代与限流的生产配置；患者域切换
  全流程（草案，未验收）；标签唯一索引的实际建索引操作（方案阶段）。
