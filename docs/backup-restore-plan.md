# 完整备份与恢复能力方案（T22）

> 状态：方案稿。本方案**未经真实环境演练**，所有数字（RPO/RTO/保留期）均为
> 建议值，须经业务确认后才有约束力；演练本身按 §4 的清单在隔离环境执行，
> 演练结果回填本文件后方可视为「具备恢复能力」。

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

- 本方案未经真实环境演练；RPO/RTO/保留期均为建议值，待业务确认。
- `backup_mongodb.py` / `verify_restore.py` 未在真实 mongodump / Mongo 实例
  上跑过端到端（单测用打桩验证命令组装与对账逻辑）；首次真实执行建议先对
  隔离演练实例做一次备份→恢复→对账闭环。
- 脚本未覆盖媒体目录的文件级备份与密钥保管（§1.2/§1.3 为人工流程），也未
  实现异地上传与加密（推荐 age/gpg 外部流程）。
- 副本集扩为多节点后，应把备份读偏好切到 secondary 并复核 RPO。

## 6. 后续增强（不阻塞本方案）

- manifest 增加 `files` 段记录媒体目录条目数，纳入 verify 对账；
- 备份后自动校验 SHA256 与可打开性（`mongodump --archive` 头部探测）；
- 调度器 systemd unit 示例与告警（备份失败需可见，不能静默失败——现有
  `backup_schedule` 的 except-日志模式即静默失败反例）；
- 管理端独立 `dump_frequency` 设置（§3）。
