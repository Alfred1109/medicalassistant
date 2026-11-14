# 完整备份与恢复能力方案（T22）

> 状态：方案稿 → 已于 2026-11-14 在本机隔离实例完成首次实机闭环演练
> （备份→恢复→对账→负向用例，见文末「演练记录」）。所有数字（RPO/RTO/保留期）
> 仍为建议值，须经业务确认后才有约束力。

## 0. 一句话结论

业务 JSON 导出（`backend/app/operations/data_export.py`，含
`runtime.backup_schedule` 的定时落盘）明确标识 `restorable: false`，只作
**业务层归档**，不承担恢复职责；数据库恢复的唯一依据是
`mongodump --gzip --archive` 全量归档（`backend/scripts/backup_mongodb.py`
产出 archive + manifest），恢复质量由 `backend/scripts/verify_restore.py`
对账工具在隔离环境验证。

## 1. 备份对象与形态

### 1.1 MongoDB 全库（恢复能力的主体）

- 形态：`mongodump --gzip --archive=<单文件>`（由
  `scripts/backup_mongodb.py` 包装执行，URI 参数化、缺省仅允许本机主机闸门）。
  单文件归档便于整体加密、搬运与异地存放；目录态（`--out`）仅在需要按集合
  抽取时作为人工后备手段，不作为常规产物。
- 一致性：本项目 Mongo 为**单节点副本集** `rehab_rs`
  （`deploy/mongodb/compose.yml`，mongo:7.0.16，`127.0.0.1:37021`）。
  加 `--oplog` 可得到时间点一致快照（副本集特性；单机 mongod 不可用）。
  建议：备份窗口内仍有写入时必须带 `--oplog`。当前部署**不提供高可用**，
  备份是唯一的时间点回退手段——患者域迁移提交后不可逆，其唯一回滚途径
  就是本节的全量归档恢复。
- manifest：每次备份同目录产出
  `rehab-mongodb-<UTC时间戳>.manifest.json`（format
  `rehab-mongodb-backup-manifest-v1`），记录：归档文件名/字节数/SHA256、
  掩码后的源连接串、Mongo 版本、副本集名、是否捕获 oplog、**各用户库各集合
  文档数与索引名清单**、`patient_domain_state` 单例（
  `clinical-patients-v1`）的存在性与 mode。manifest 只含元数据（计数、
  索引名），不含任何文档内容；`admin/config/local` 系统库不进 manifest。
- 明确不覆盖：`.venv`、日志（`backend/logs`、`logs/`）、业务 JSON 导出产物
  （`backend/data/backups/`）——这些可重建或属归档产物，不属于恢复依据。

### 1.2 文件/媒体存储（现状核实结果）

| 存储 | 位置 | 写入方 | 说明 |
| --- | --- | --- | --- |
| 患者反馈媒体 | `backend/data/patient-feedback/` | `app/services/rehab_feedback_service.py:27`（`MEDIA_DIR`） | 文件名 `{media_id}{suffix}`，库内存引用 |
| 练习媒体 | `backend/data/exercise-media/` | `app/api/routers/rehabilitation_router.py:39`（`EXERCISE_MEDIA`） | 文件名白名单后缀 |
| 头像 | **Mongo 内**（`users.avatar_bytes`） | `app/services/user_service.py:182` | 随 1.1 的 mongodump 一并覆盖，无独立文件 |
| 定时业务导出 | `backend/data/backups/` | `app/operations/runtime.py:106` | JSON 归档产物，随备份归档存放即可 |
| `UPLOAD_DIR` 配置 | `app/core/config.py:186`（缺省 `uploads`） | **当前无任何代码写入** | 保留在清单中以防后续启用 |

备份方式：对 `backend/data/` 下上述目录做**文件级同步**（rsync/tar 到备份
存放区），与 Mongo 归档同批次执行并在 manifest 旁记录目录条目数（可在
manifest JSON 中追加 `files` 段，本版脚本未实现，属后续增强，见 §6）。
恢复演练时先恢复 Mongo、再同步媒体目录，最后跑对账与冒烟。

### 1.3 配置与密钥（列出应纳入项，**不收集真实密钥值**）

应纳入备份（密文/受控渠道保管，与本方案归档分离存放）：

- `backend/.env` 与启动环境（含 `MONGODB_URL`、`SECRET_KEY`、
  `FORM_PLATFORM_CLIENT_SECRET`、`LLM_API_KEY`/`VISION_API_KEY`、
  `MAIL_PASSWORD`、`REDIS_PASSWORD` 等）；
- `deploy/`（mongodb/nginx 的 compose、初始化脚本、证书）；
- 注意 `SECRET_KEY`（`app/core/config.py:116`）：**未在环境显式提供时每次
  启动随机生成**——恢复后不还原同一 `SECRET_KEY` 会使全部已签发 token 失效，
  属「可恢复但会强制全员重新登录」的软失败，应纳入环境备份避免。

## 2. 恢复目标与保留策略（建议值，待业务确认）

### 2.1 RPO / RTO 建议

| 项 | 建议值 | 说明 |
| --- | --- | --- |
| RPO | ≤ 24h（每日全量）；高频写入期可加密至 ≤ 1h | 每日一次全库归档；对患者域迁移等**高风险变更，变更前强制手工加备一次**，使该操作的 RPO 趋近 0 |
| RTO | ≤ 4h（含恢复 + 对账 + 冒烟） | 预估：mongorestore 单机库约 10–30 分钟量级，对账与冒烟约 1h，余量为人工决策与隔离环境准备 |
| 备份窗口 | 低峰（建议 UTC+8 凌晨） | 副本集单节点，dump 期间有读压力；带 `--oplog` 保证窗口内一致性 |

### 2.2 保留策略（建议：GFS 梯度）

- 每日档保留 7 份、每周档保留 4 份、每月档保留 6 份；每次患者域迁移等
  不可逆变更前的手工档**保留至该变更稳定运行满 1 个月**。
- 存放要求：
  - 备份目录权限收紧（属主只读），`manifest` 与 `archive` 同级同权存放；
  - **加密存放**：archive 文件用 age/gpg 公钥加密后落备份区/异地，私钥线下
    另管；业务 JSON 导出含患者明文（见 `data_export.py` manifest 的
    `contains_patient_information: true`），媒体目录为原始患者材料，两者
    **同等加密**，绝不以明文形式离开生产主机；
  - 异地副本只增密文：患者数据不以明文外流，密钥与密文分地存放；
  - manifest 虽无文档内容，但库名/集合名即部署信息，与 archive 同等保管。

## 3. 与现有 backup_schedule 的关系（结论：并存，职责不同）

现状（`backend/app/operations/runtime.py:72-114`）：`BackupSchedule` 是应用
内每小时唤醒的 asyncio 循环，读 `system_settings.backup_frequency`
（hourly/daily/weekly/monthly，管理端可调），到期把
`data_export_bytes` 的**受限业务 JSON**写到 `backend/data/backups/` 并记
`last_scheduled_export_at`。它从未产出过可恢复的备份，管理端
`backup_frequency` 配置实际只调业务导出节奏。

建议：**并存、不复用执行通道**。

- `backup_schedule`（业务 JSON 导出）继续承担「业务层归档/人工看数据」，
  不改语义、不承担恢复（其产物 manifest 已自证 `restorable: false`）；
- Mongo 全库备份走 `scripts/backup_mongodb.py`，由**应用之外的调度器**
  （systemd timer / cron）周期执行。理由：
  1) 备份必须独立于应用生命周期——恢复场景往往发生在应用已不可用时，
     备份链路不应依赖 FastAPI 进程存活；
  2) mongodump 是独立二进制，运行在宿主机而非应用容器内；
  3) `deploy/mongodb/README.md` 已声明正式部署需「另行配置账号、网络隔离、
     备份」，备份属部署层职责；
  4) 复用 `backup_frequency` 配置看似省事，实则把 RPO 决策绑到了一个
     语义为「业务导出频率」的设置上，容易误配。
- 若后续希望管理端能调备份频率，新增独立设置项（如 `dump_frequency`）
  映射到调度器，而不是复用 `backup_frequency`。

## 4. 恢复演练流程（隔离环境）

前置：隔离环境 = 独立临时 Mongo 容器（不要指向生产库；演练实例与本机闸门
兼容，`--allow-remote` 仅在演练实例不在本机时使用）。

步骤：

1. 取一份最近归档 + manifest（密文先解密到演练机）。
2. 启动隔离实例（示例，端口避开 37021）：
   `docker run -d --name rehab-restore-drill -p 38031:27017 mongo:7.0.16 mongod --replSet drill_rs`
   并按 `deploy/mongodb/init-replica.js` 同法初始化单节点副本集。
3. 恢复：
   `mongorestore --uri mongodb://127.0.0.1:38031/?replicaSet=drill_rs&directConnection=true --gzip --archive=<archive> --drop`
   （带 `--oplog` 的归档加 `--oplogReplay`。）
4. 对账（只读工具）：
   `python -m scripts.verify_restore --manifest <manifest> --uri mongodb://127.0.0.1:38031/?replicaSet=drill_rs`
   要求退出码 0：各库各集合计数一致、manifest 记录的索引名全部存在、
   `patient_domain_state` 存在性与 mode 一致；多出的集合只记信息，人工判断。
5. 恢复后验证清单：
   - [ ] 集合计数对账（verify_restore 差异报告为空）；
   - [ ] 索引存在性（manifest 索引名清单比对；重点：
         `clinical_patient_id_unique`、`patient_account_unique`、
         messages 幂等唯一索引 `uniq_conversation_sender_client_message_id`）；
   - [ ] 患者域状态文档：`patient_domain_state._id == "clinical-patients-v1"`，
         mode 与 manifest 一致（canonical 库恢复后必须仍是 canonical，
         否则 `require_canonical` 会拒绝服务）；
   - [ ] 业务冒烟：以恢复库启动应用（指向演练实例），登录一个账号、
         读取患者列表、发起一次随访记录读写；
   - [ ] 媒体目录条目数与源目录一致（§1.2 目录同步产物）；
   - [ ] 记录演练用时 → 对照 RTO 建议值。
6. 演练后处置：销毁演练容器与卷，演练发现的问题回填本文件。
7. 演练频率建议：季度一次；任何患者域迁移执行**前**做一次。

## 5. 边界声明

- 方案已于 2026-11-14 在本机隔离实例完成首次实机闭环演练（见文末演练记录）；
  RPO/RTO/保留期仍为建议值，待业务确认。
- `backup_mongodb.py` / `verify_restore.py` 已在真实 mongodump / Mongo 实例上
  跑通端到端（含负向用例；单测打桩覆盖命令组装与对账逻辑）。
- 脚本未覆盖媒体目录的文件级备份与密钥保管（§1.2/§1.3 为人工流程），也未
  实现异地上传与加密（推荐 age/gpg 外部流程）。
- 副本集扩为多节点后，应把备份读偏好切到 secondary 并复核 RPO。

## 6. 后续增强（不阻塞本方案）

- manifest 增加 `files` 段记录媒体目录条目数，纳入 verify 对账；
- 备份后自动校验 SHA256 与可打开性（`mongodump --archive` 头部探测）；
- 调度器 systemd unit 示例与告警（备份失败需可见，不能静默失败——现有
  `backup_schedule` 的 except-日志模式即静默失败反例）；
- 管理端独立 `dump_frequency` 设置（§3）；
- manifest 计数采集时点问题：manifest 在 mongodump 结束**之后**经独立连接
  采集（演练记录 3.6 实测发现）。备份窗口内有并发写入时，manifest 计数可能
  与 archive 内容漂移，造成对账「假差异」。根治需把计数对齐到 `--oplog` 的
  截止时间点（或 dump 前后各采一次取交集），属脚本增强项。备份窗口内并发
  写入少（生产低峰执行）时影响可忽略。

## 7. 演练记录（2026-11-14，本机隔离实例）

> T33 首次实机闭环演练：备份→恢复→对账→负向用例，全部通过。
> 本节为实测记录，含环境缺口与踩坑，供下次演练直接复用。

### 7.1 环境与工具路径（如实记录）

- 本机 **无** mongodump / mongorestore / mongosh 二进制，均经 docker 镜像
  `mongo:7.0.16`（与本机 rehab_rs 同镜像同版本）执行。
- 备份源：rehab_rs 单节点副本集
  `mongodb://127.0.0.1:37021/?replicaSet=rehab_rs&directConnection=true`。
- 恢复目标：一次性容器 `rehab-restore-drill-t33`（mongo:7.0.16，
  `mongod --replSet drill_rs`，宿主端口 127.0.0.1:38031），rs.initiate 单节点
  初始化后接收 `--oplogReplay` 恢复。演练后已销毁。
- mongodump 调用路径（本机无二进制的替代方案）：

  ```sh
  docker run --rm --network host -v /tmp:/tmp --entrypoint mongodump \
      mongo:7.0.16 mongodump --uri <uri> --gzip --archive=<路径> --oplog
  ```

  `--network host` 使 `--uri` 中 `127.0.0.1` 语义与宿主一致；`-v /tmp:/tmp`
  使 `--archive=` 宿主路径在容器内同路径可写；`--entrypoint mongodump` 见
  坑 1。经 `backup_mongodb.py --mongodump <wrapper脚本>` 参数接入，未改脚本。

### 7.2 踩坑（下次演练直接绕开）

1. **mongo 镜像 entrypoint 强制降权**：`docker run mongo:7.0.16 mongodump ...`
   会被 entrypoint `gosu` 到 `mongodb` 用户（uid 999），对宿主属主目录无写
   权限 → `permission denied`。`--user 0:0` 也拦不住（entrypoint 检测 uid=0
   且命令为 `mongo*` 时仍降权）。必须 `--entrypoint mongodump` 绕过。
2. **容器内路径 ≠ 宿主路径**：`-v /tmp/drill-t33:/drill` 时容器内归档路径是
   `/drill/backup/...`；mongorestore 传宿主路径会报 `no such file or
   directory`。wrapper 改挂 `/tmp:/tmp` 消除换算。
3. **镜像内 mongodump 为 100.11.0 但不认 `--nsInclude`**（官方 database-tools
   支持；镜像为二次打包版本，工具二进制属主异常 uid 1000）。本次未依赖该参数，
   备份全库归档不受影响，但按库抽取的场景不可用该镜像。
4. **演练源实例前身崩溃循环（环境缺口，已处置）**：演练开始时 rehab_rs 容器
   因 fd 耗尽崩溃循环（`epoll: Too many open files`），数据卷内有约 4.2 万个
   `.wt` 文件（今日此前演练残留的孤儿集合/索引文件），而 compose 未配置
   ulimit，容器默认软限制 nofile=1024。处置：临时以同数据卷、同副本集名、
   `--ulimit nofile=65536:65536` 起替代容器顶上 37021 端口，并清理 18 个
   pytest 残留库后完成演练。**遗留改进：`deploy/mongodb/compose.yml` 应为
   mongo 服务加 `ulimits.nofile`（本次未改动该文件，属部署层修复项）**。

### 7.3 演练步骤与实测数据

合成数据（独立库 `drill_t33_patients_demo` / `drill_t33_biz_demo`）：
`clinical_patients_demo` 500 条（含 unique 索引 `clinical_patient_id_unique`、
`patient_name_idx`）、`messages_demo` 1200 条（含幂等唯一索引
`uniq_conversation_sender_client_message_id`）、`patient_domain_state` 单例
（mode=canonical，仿迁移产物）、`feedback_demo` 300 条。备份窗口内另有并行
任务的测试库在写入（rehab_comm_revocation_*），故本次走 `--oplog` 时间点一致
路径——与 §1.1 的生产建议一致。

| 步骤 | 实测命令（要点） | 耗时 | 结果 |
| --- | --- | --- | --- |
| 备份 | `.venv/bin/python -m scripts.backup_mongodb --uri <rehab_rs> --oplog --output-dir /tmp/drill-t33/backup --mongodump <wrapper>` | **0.84s** | archive 28,279 字节 + manifest；SHA256 记录完整 |
| 恢复 | `docker exec rehab-restore-drill-t33 mongorestore --host 127.0.0.1:27017 --gzip --archive=/drill/backup/<archive> --drop --oplogReplay` | **0.90s** | 2069 文档恢复成功，0 失败 |
| 对账 | `.venv/bin/python -m scripts.verify_restore --manifest <manifest> --uri mongodb://127.0.0.1:38031/?directConnection=true` | **0.59s** | 退出码 0；20 库 / 43 集合 / 48 索引全部一致；`extra_collections` 空 |

manifest 校验项（全部符合预期）：
- 计数与真实库逐一核对一致（含 drill 库 500/1200/1/300）；
- `source_uri_masked` 掩码生效；日志与 manifest 中无明文连接串
  （mongodump 子进程输出亦经 `mask_text` 掩码，未回显 URI）；
- `mongo_version=7.0.16`、`topology.replica_set=rehab_rs`、`oplog_captured=true`；
- `patient_domain_state`：present=true，mode=canonical。

### 7.4 负向用例（全部按预期）

| 用例 | 操作 | 退出码 | 差异报告 |
| --- | --- | --- | --- |
| 篡改计数 | 恢复库 `feedback_demo` 插入 3 条 | 1 | `count_mismatch`（期望 300 / 实际 303），database/collection 定位准确 |
| 删状态单例 | 恢复库删除 `patient_domain_state` 文档 | 1 | 同时报 `count_mismatch`（1→0）与专项 `patient_domain_state_mismatch`（present/mode 双字段） |

### 7.5 RTO 实测校准

- 实测（本机、库规模 ~2 千文档 / 20 库）：mongodump 0.84s → mongorestore
  0.90s → 对账 0.59s，**恢复主链路合计 ~2.3s**；隔离实例容器启动 + rs
  初始化 ~10s。远优于 §2.1 的 RTO ≤ 4h 建议值。
- 但注意量级差异：本机库为开发数据（catalog 仅 ~2 千文档）。§2.1 的
  「mongorestore 10–30 分钟」预估针对生产数据量，维持不变；本机演练的价值
  在于验证链路可行性与对账工具行为，而非推断生产 RTO。
- 并发写入场景（--oplog 路径）已验证可行；备份窗口内并发写入下对账零差异。

### 7.6 脚本修复与已知限制

- 修复（`backend/scripts/backup_mongodb.py`）：mongodump 非零退出时清理
  **半成品归档**（中途失败如源库断连会留下部分写入的 archive，此前会残留在
  输出目录，可能被误当作可用备份）。补单测
  `test_main_failure_removes_partial_archive`（tests/test_backup_restore_tooling.py）。
- 已知限制（未修，见 §6）：manifest 计数在 dump 结束后采集，备份窗口内有
  并发写入时可能产生「假差异」；本次演练恰有并行任务在写，未触发（写入发生
  在 manifest 采集前）。低峰备份窗口下影响可忽略。
- 本次演练未覆盖（按方案属人工流程）：媒体目录文件级同步（§1.2）、密钥
  保管（§1.3）、加密与异地上传。

### 7.7 演练后处置

- rehab_rs 上演练库（`drill_t33_*`）已 drop；恢复容器 `rehab-restore-drill-t33`
  已销毁；/tmp/drill-t33 临时目录（含归档，内含库内容元数据）已删除。
- 替代容器处置见 §7.2 坑 4。
