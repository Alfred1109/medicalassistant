# 患者档案第二波段（canonical 模式启用）切换方案草案

> **状态：草案（DRAFT）。** 本文档只描述计划，切换本身未经任何验收。
> 不得据此宣称患者档案迁移、切换或上线已完成。所有行号引用基于撰写时
> 的工作区状态（2026-11-14），后续代码变更须先复核引用再执行。

---

## 1. 目标与前置门槛

### 1.1 目标

在第一波段（legacy 读取收敛 + 授权内核域分派，见
`docs/architecture-convergence.md`）基础上，把业务域逐波切换到
`clinical_patients` canonical 域：授权内核按 `patient_domain_state`
单例（`clinical-patients-v1`）分派（`backend/app/core/patient_access.py:38`）、
患者实体由 `ClinicalPatientRepository` 承载、账号↔患者关系由
`patient_account_links` 显式承载。每一波都是"域开关 + 实现替换 + 门闩移除"
的原子动作，可独立回拨。

### 1.2 前置门槛（任何一波启动前必须全部满足）

| 门槛 | 内容 | 依据 |
|---|---|---|
| G1 盘点干净 | 在**真实库**跑一次只读盘点 `backend/scripts/patient_reference_audit.py`（用法见 `docs/patient-reference-audit.md`），`ambiguous` 逐组人工核实并有书面处置结论；`dangling`/双形态有处置决策（治理或书面豁免）。盘点结果归档为切换证据。 | `docs/patient-reference-audit.md:52-90` |
| G2 迁移演练通过 | `backend/scripts/manage_clinical_patients.py` 在隔离实例完成 inspect→apply→复查演练；manifest 比对一致；迁移保留原 `users._id` 作为患者主键（`backend/app/patients/migration.py:68-81`），`patient_account_links` 以 `legacy_same_document` 来源逐账号建立（`migration.py:120-121`）。生产 apply 尚未执行，CLI cutover 当前禁用（`backend/app/patients/README.md:41-43`）。 | `backend/app/patients/README.md:31-79` |
| G3 内核分派全绿 | `app/core/patient_access.py` 双模式（legacy/canonical）+ fail-closed（未知状态/读取失败一律 503 `PATIENT_DOMAIN_STATE_UNAVAILABLE`，`patient_access.py:40-47`）测试全部通过；canonical self 解析经 `repo.resolve_self`（仅 verified 链接，`backend/app/patients/repository.py:114`）在隔离库验证。 | `backend/app/patients/README.md:81-109` |
| G4 备份可恢复 | 完整数据库备份 + **独立恢复演练**成功。业务 JSON 导出不是备份（仍含患者信息、字段有限，`docs/architecture-convergence.md:32`）；迁移工具的快照目录（0700/0600）也不替代备份（`backend/app/patients/README.md:71-74`）。 | `docs/architecture-convergence.md:22,32` |
| G5 维护窗口写者排除 | 迁移/切换窗口内，应用写者、后台调度、外部直连工具均被部署流程排除；工具本身无法证明不存在未知外部 Mongo 写者（`backend/app/patients/README.md:64-69`），必须以部署流程兜底。 | `backend/app/patients/README.md:46-69` |

任一门槛不满足，后续波次一律不启动。

---

## 2. 波次划分

波次间依赖：**波次 0 是所有波的前置；波次 1 是波次 2–6 的前置；同波内
条目原子交付。** 每波回滚方式统一为"域开关回拨"：以**显式域开关状态
变更**执行（见 §5.1 回拨 SOP；**禁止以删除状态文档代替回拨**——当前
实现把「无状态文档」解释为 legacy 默认域，删文档会静默降级回 users
路径，无 503、无告警、canonical 数据仍在但不再被消费）；canonical 侧
该窗口内的写入**不会自动回流 legacy**，须按 §5.2 R9 的对账清单逐项
核实后再重新启用。

### 波次 0：门槛核验（不切换任何域）

- **启用范围：** 无。只完成 §1.2 G1–G5 并留证。
- **涉及文件：** 只读运行 `backend/scripts/patient_reference_audit.py`、
  `backend/scripts/manage_clinical_patients.py`（隔离实例）。
- **门闩移除条件：** 不适用。
- **验证清单：** 盘点报告归档；迁移演练 manifest 一致；隔离副本集上
  内核双模式测试 + 事务回滚 + 无事务拒绝（对照 `docs/architecture-convergence.md:29`）；
  恢复演练后业务抽查。
- **回滚方式：** 不适用（无变更）。

### 波次 1：授权内核与读取面收敛

- **启用范围：** `patient_domain_state` 置 canonical 后，患者对象加载、
  本人解析、医护范围查询、姓名搜索全量走 canonical。覆盖患者列表/本人、
  随访读取范围、健康档案、设备读取、康复列表、质控列表——不能只切单个
  读取函数（`docs/architecture-convergence.md:16`）。
- **涉及域与文件：**
  - `backend/app/core/patient_access.py`：`load_patient_doc`（:112，canonical
    分支不读 users）、`ensure_self_patient_access`（:64-70，canonical 经
    `repository.resolve_self`）、`assigned_scope_query`（:98-110，canonical
    范围已含 `status=active`）。
  - `backend/app/patients/repository.py`：`get`（:107）、`resolve_self`（:114）、
    `matching_name_ids`（:157）、`assigned_query`（:99）。
  - 各域读取入口（router → service）随内核分派生效，无需逐个改写。
- **第一波段缺口现状（撰写时已落地、以 T1 验收为准）：** 姓名搜索
  （`repository.py:157` `matching_name_ids` + 姓名索引 `repository.py:79`）、
  `is_active`→`status` 映射（canonical 分支不读 `users.is_active`，
  `patient_access.py:100`）、`devices.patient_id` 索引
  （`backend/app/db/indexes.py:52-56` `device_patient_query`）。
- **门闩移除条件：** 本波无既有 503 门闩（门闩集中在写路径域）。
- **决策项（T50 对抗审查登记，波次 1 启用前必须业务确认）：** 停用患者对
  医护的可见性口径。当前实现是**统一 404**：`load_patient_doc` 的
  canonical 分支把 `status != "active"` 一律按不存在处理（404
  `PATIENT_NOT_FOUND`），经 `ensure_patient_access` 与各域对象级访问路径
  生效；而 legacy 域中部分消费方的现状是「被分配医护仍可读停用患者
  （is_active=False）」。因此 canonical 的统一 404 是**收紧而非对齐**。
  波次 1 启用前需业务确认：「统一 404」（现状实现，见
  `backend/app/core/patient_access.py` canonical 分支）还是「消费方级
  status 策略」（如随访/健康档案允许被分配医护继续读停用患者）。确认
  结论回写本节后方可置 canonical。
- **待办登记（T50 对抗审查，随 T44 落地后补齐）：**
  `backend/app/integrations/forms/service.py` 的 `_verify_patient_assignment`
  catch-all 把一切 `PatientAccessError` 降级为集成侧 403
  `PATIENT_NOT_ASSIGNED`，域状态不可用 503
  `PATIENT_DOMAIN_STATE_UNAVAILABLE` 被吞并（T50 缺陷 2 的第四处同型点）。
  该文件域是并行任务 T44 的在途改动，本任务不修；T44 合入后按缺陷 2 同款
  `error_code` 分流修法补齐（503 透传、其余保持原语义）。
- **验证清单：**
  1. 双模式合同测试：同名患者列表 / 本人访问 / 医护范围 / 姓名搜索在
     legacy 与 canonical 结果一致（患者集合与字段差异除外）。
  2. 隔离库验收：迁移后的库上跑医护列表、本人、随访范围、设备读取冒烟。
  3. fail-closed：状态文档缺失/未知版本/读取失败 → 503 且不回退 legacy。
  4. 全量回归（对照本轮基线 687 passed / 262 skipped，
     `docs/architecture-convergence.md:38`）。
  5. canonical 写路径冒烟（T50 对抗审查「观察」，栅栏载体拆分前的已知
     限制）：置 canonical 后，workspace 报告审核写入与 device fence 写
     路径必须逐项冒烟——两条写路径的并发栅栏仍落在 `users` 载体（§3），
     canonical 下账号与患者文档拆开，启用前须实测并发撤权不假报成功。
- **回滚方式：** 域开关回拨 legacy。读取面无写入残留，回拨即恢复。

### 波次 2：康复发布与人工质控写路径（含栅栏载体拆分首落地）

- **启用范围：** 康复方案发布/反馈、人工质控问题的授权与写入走 canonical；
  **栅栏载体拆分在本波先行落地**（见 §3），因为 canonical 患者文档已不在
  `users`，沿用 `users._access_fence` 的栅栏在 canonical 模式下失效。
- **涉及域与文件：**
  - `backend/app/services/rehab_publication_service.py`：`_legacy` 门闩
    （:100-102 `REHAB_PATIENT_DOMAIN_UNSUPPORTED`）、`_account`（:105-113，
    canonical 需拆分账号对象与患者对象）、`_access_fence`（:114-122）、
    `_authorize`（:124 起）。
  - `backend/app/services/quality_issue_service.py`：`_actor` 门闩
    （:86-93 `QUALITY_PATIENT_DOMAIN_UNSUPPORTED`）、`_fence`（:78-84，
    TODO 注明切 canonical 时随载体迁移）。
  - 栅栏新载体（§3）：账号栅栏载体 + `clinical_patients` 实体栅栏字段。
- **门闩移除条件：** 两处门闩的替换实现（canonical 账号解析经 verified
  链接 + 患者对象加载 + 双载体栅栏事务复核）在隔离副本集上通过并发撤权
  与回滚验证后，才允许删除门闩代码并置 canonical。
- **验证清单：**
  1. 隔离副本集：并发撤权场景（栅栏 matched_count 复核失败 → 409/503，
     不假报成功）；无事务环境拒绝写入（对照
     `docs/architecture-convergence.md:9,29`）。
  2. 发布快照与版本绑定回归（`docs/architecture-convergence.md:34`）。
  3. 质控患者范围与过程质控共用范围回归（commit b1eadac 引入的共用患者
     范围与事务复核）。
  4. 全量回归 + `test_rehab_publications.py`、质控合同测试。
- **回滚方式：** 域开关回拨。门闩代码保留到本波验收通过后才物理删除；
  回拨窗口内 canonical 侧发布/质控写入按 §5.2 R9 对账。

### 波次 3：质控过程监测与随访提醒

- **启用范围：** 过程质控患者范围、随访提醒生成与并发栅栏走 canonical。
- **涉及域与文件：**
  - `backend/app/services/quality_monitoring_service.py`：门闩（:86
    `QUALITY_PATIENT_DOMAIN_UNSUPPORTED`）及范围歧义防护（:93-118）。
  - `backend/app/services/followup_reminder_service.py`：两处门闩（:119、
    :180，`REMINDER_PATIENT_DOMAIN_UNSUPPORTED`）、`_reminder_fence`
    （:74-81）。
  - `backend/app/services/followup_service.py`：`_reminder_fence` /
    `_access_fence`（:312-317、:342-347）及投影排除清单（:68-69）。
  - `backend/app/services/quality_process_queries.py`：患者集合常量
    `PATIENT_USERS_COLLECTION = "users"`（:11）与 `$lookup`（:78）。
- **依赖：** 波次 2（栅栏拆分与账号解析已定形）；波次 1（读取范围）。
- **门闩移除条件：** 提醒账号解析经 `patient_account_links`（无链接患者
  跳过并计入重试，不做姓名/ID 推断）+ 过程监测 `$lookup` 切换到
  canonical 患者集合且结果与 legacy 对账一致后移除。
- **验证清单：** 提醒到期扫描（`reminder_due_scan` 索引路径）双模式对账；
  部分提醒失败重试语义（`followup_reminder_service.py:211`）；过程质控
  快照聚合结果 diff；全量回归。
- **回滚方式：** 域开关回拨；提醒是幂等重试型任务，回拨后由重试兜底。

### 波次 4：统计聚合与报告调度

- **启用范围：** 统计分析、定时报告、过程质控跨域聚合的患者集合切换。
- **涉及域与文件：** 患者集合名已集中为模块常量，各改一处：
  - `backend/app/services/analytics_service.py:9`（`PATIENTS_COLLECTION_NAME`）
  - `backend/app/services/report_scheduler_service.py:25`
  - `backend/app/services/quality_process_queries.py:11`
    （若波次 3 已切则此处仅为复核）
- **依赖：** 波次 1、2、3（被统计的域已切换，否则统计口径割裂）。
- **门闩移除条件：** 无显式门闩；条件是双模式聚合结果对账一致。
- **验证清单：** 合成数据下双模式聚合逐指标 diff；`test_rehab_statistics_contract.py`
  与统计合同测试；定时报告生成的患者信息抽查。
- **回滚方式：** 域开关回拨 + 常量回改（各一处，回滚成本低）。

### 波次 5：通信通知送达与身份/表单集成路径

- **启用范围：** 通信通知的患者侧接收人解析、表单填报/身份集成的并发
  栅栏与患者校验走 canonical。
- **涉及域与文件：**
  - `backend/app/services/communication_service.py`：会话成员/通知接收人
    保持账号 ID（:256-261 注释明确 canonical 波段经 `patient_account_links`
    解析）；**canonical 患者通知送达经链接解析接收账号，无链接患者跳过**
    （`PATIENT_ACCOUNT_UNAVAILABLE` 兜底已存在）。
  - `backend/app/integrations/forms/service.py`：`fill_use_revision` 栅栏
    （:299、:612-618）。
  - `backend/app/integrations/identity/service.py:59`：`fill_use_revision`。
  - `backend/app/clinical/workspace.py:474-487`：报告访问栅栏
    `report_access_revision`（TODO 已注明 canonical 需改为临床患者文档/
    账号链接载体）。
  - `backend/app/core/device_access.py:35-39`：`_device_access_fence`。
- **依赖：** 波次 2（栅栏拆分定形）；波次 1（链接解析可用）。
- **门闩移除条件：** 通知送达的无链接跳过路径与 `PATIENT_ACCOUNT_UNAVAILABLE`
  兜底在隔离库验证；各栅栏按 §3 双载体迁移完成。
- **验证清单：** 通信合同测试（`test_communication_contract.py`）；并发撤权
  专项（对照 `docs/architecture-convergence.md:33`）；工作台报告写入
  版本绑定回归；`test_integration_forms_contract.py`。
- **回滚方式：** 域开关回拨；通知缺失不阻塞通信主流程。

### 波次 6：新患者创建路径（people_import → create_from_source，决策后）

- **启用范围：** `people_import` 不再向 `users` 插入新患者
  （`backend/app/integrations/forms/people_import.py:86` 是唯一仍向
  `users` 插入的写路径），改走 `create_from_source`
  （`backend/app/patients/repository.py:180`，支持外部事务参与）。
- **依赖：** 波次 1–5 全部完成；§4 业务决策清单全部有结论。
- **门闩移除条件：** 不适用（本波是业务决策波，见 §4）。
- **验证清单：** 隔离库导入演练：canonical 实体创建 + 外部引用 + 审计
  原子提交；`create_from_source` 的索引前置检查/事务内 hint 语义
  （`backend/app/patients/README.md:121-128`）；`test_project_people_import.py`
  改造后回归。
- **回滚方式：** 本波以**代码路径开关**回滚（导入入口切回旧实现）；
  不涉及存量数据。

---

## 3. 栅栏载体拆分方案与事务影响

### 3.1 现状：并发栅栏全部落在 `users` 账号文档

| 栅栏字段 | 位置 | 语义 |
|---|---|---|
| `_access_fence` | `followup_service.py:312-317`、`quality_issue_service.py:81-84`、`rehab_publication_service.py:119-122` | 账号/患者并发状态 |
| `_reminder_fence` | `followup_service.py:342-347`、`followup_reminder_service.py:74-81` | 提醒并发 |
| `_device_access_fence` | `device_access.py:35-39` | 设备访问并发撤权 |
| `fill_use_revision` | `forms/service.py:299,612-618`、`identity/service.py:59` | 填报凭证消费 |
| `report_access_revision` | `workspace.py:474-487` | 报告访问并发（含归属字段快照比较） |

这些字段混在账号文档上：既有"登录账号被撤权"的语义，又有"患者归属
（practitioners/health_managers 快照）变化"的语义。legacy 域中账号与患者
同文档，两种语义共享一个载体成立；canonical 域拆开后不成立。

### 3.2 拆分方案

拆为两个载体：

1. **账号栅栏载体**：登录账号的并发状态（撤权、禁用、登录态）。承载
   `fill_use_revision`、`report_access_revision` 的账号侧计数、
   `_device_access_fence` 的账号侧复核。候选载体：保留在 `users` 文档
   （canonical 模式下 `users` 只读，`backend/app/patients/README.md:20-21`，
   需豁免"只读"约定仅允许栅栏 `$inc`）或独立 `account_fences` 集合。
   推荐后者：不污染 `users` 只读约定，账号撤权写入与栅栏递增互不干扰。
2. **患者实体栅栏载体**：临床患者文档的归属/状态并发（医护分配变化、
   `status` 变化）。承载 `_access_fence`、`_reminder_fence` 的患者侧、
   `report_access_revision` 的归属字段快照比较。候选载体：
   `clinical_patients` 文档新增栅栏字段（不进入业务投影，参照
   `followup_service.py:68-69` 的投影排除惯例）。

### 3.3 事务影响

- 现有栅栏均为"同事务 `$inc` + `matched_count==1` 复核"（如
  `workspace.py:484-487`、`rehab_publication_service.py:119-122`）。
  legacy 域一次 `$inc` 命中一个文档即同时覆盖账号与患者两种语义；
  拆分后**同一事务内需对两个载体各复核一次**：账号栅栏 `$inc` 失败 →
  账号态变化（撤权）；实体栅栏失败 → 归属变化。两次复核都必须在同一
  Mongo 事务内，失败即整体回滚，不得顺序写入或只复核其一
  （对照 `docs/architecture-convergence.md:9`）。
- `workspace.py:481-485` 的快照比较（role/is_active/source_project_id/
  practitioners/health_managers）拆分后拆到对应载体：账号字段比较走
  账号载体查询，归属字段比较走 `clinical_patients` 实体文档。
- 迁移期一致性：切换时存量栅栏计数不迁移（计数仅作 CAS 比较用，无业务
  含义），各载体从当前值重新起算即可；但**必须保证切换窗口内旧载体停止
  递增**，否则回拨后旧计数失效。
- 验证要求：隔离副本集重跑并发撤权与写入回滚专项（对照
  `docs/architecture-convergence.md:29,33`），覆盖"账号变 + 实体不变"、
  "实体变 + 账号不变"、"双变"三种交错。

---

## 4. 新患者创建路径决策点（people_import → create_from_source）

以下问题需业务确认后，波次 6 才能进入实现：

1. **导入患者是否需要登录账号？** `create_from_source` 不创建账号、
   不分配医护（`backend/app/patients/README.md:7-10,128`）；而
   `people_import` 现在直接向 `users` 插入带登录属性的文档
   （`people_import.py:86`）。若导入患者无需登录，是否完全不再写
   `users`？若需要登录，账号由谁、在什么审核后创建？
2. **医护分配如何落 canonical？** `assign_imported_role` /
   `set_imported_care`（`people_import.py:105-163`，直接写 `users` 归属
   字段）在 canonical 域对应 `clinical_patients.practitioners /
   health_managers`，且列表从空开始（README:8-9）。导入时的分配是保留
   还是改为导入后经审核流程分配？
3. **身份唯一性映射。** `source_person_key` 唯一索引
   （`people_import.py:25-26`）与 canonical 来源身份唯一性（origin +
   system + environment + 全局来源患者 ID，README:15-17）如何对应？
   重复导入的幂等语义（现有 `find_one` 查重，`people_import.py:54`）
   在 canonical 侧如何表达？
4. **`external_patient_links` 指向问题。** `local_patient_id` 硬约束
   24 位（`backend/app/integrations/forms/patient_links.py:34`）且经
   `ObjectId.is_valid` 归一（:95-97），当前语义指向 `users._id`。
   切换后 `create_from_source` 的患者使用 ObjectId 新命名空间
   （仅适用全新来源患者），外部链接应指向 `users._id` 还是
   `clinical_patients.patient_id`？两集合主键同为 24-hex 但命名空间
   不同，唯一索引按集合隔离，混指风险须在决策时排除。
5. **历史已导入未激活患者的归属。** 迁移工具只迁移
   `role:"patient"` 文档（`migration.py:69`）；people_import 历史插入
   文档的 role/激活形态需盘点确认，是否全部纳入迁移范围。
6. **失败 run 的重放语义。** `sync_runs.py:54` 只把 `people_import`
   失败 run 标记为 failed；切换后失败重放是走 `create_from_source`
   重试还是人工介入？
7. **审计与审核人要求。** `create_from_source` 要求调用方先核实远端
   引用并人工审核（reviewer + evidence，README:8-10）；导入批量的
   reviewer/evidence 由谁签署？

---

## 5. 回拨 SOP 与风险清单

### 5.1 回拨 SOP：域开关回拨的执行口径

`domain_mode` 的语义是「无状态文档 = legacy 默认域」
（`backend/app/patients/repository.py:38-62`）。这对全新部署是正确默认，
但它同时意味着**删除状态文档会静默回退 legacy**：无 503、无告警、
canonical 三集合原样保留却不再被任何内核入口消费，fail-closed 保障
整体失效（`backend/tests/test_patient_domain_e2e_drill.py` 回拨口径用例
固化了该语义）。因此回拨执行口径明确如下：

1. **回拨必须以显式域开关状态变更执行**：把 `patient_domain_state`
   单例的 `mode` 显式改回 legacy，或采用专用的显式回拨开关。变更全程
   留痕（变更单 + 复核人），不允许任何「顺手删文档」式回拨。
2. **禁止删除状态文档**：删除即触发上述静默降级——回退看似成功，
   实际不留任何失败信号，只能靠监控与对账事后发现。状态文档纳入
   备份与恢复演练（G4）与变更管理范围。
3. **实现前置条件（切换门槛）**：当前 `domain_mode` 对一切已存在但
   `mode != canonical` 的状态文档 fail-closed 503（显式写入
   `mode: "legacy"` 也会被拒绝），即代码尚无「显式 legacy」合法状态。
   在生产启用 canonical 前，必须先落地显式回拨载体（专用开关，或让
   `domain_mode` 接受受控的显式 legacy 状态）；载体落地前 canonical
   不具备安全的显式回拨路径，本节第 1 条不可执行，canonical 不得启用。

> **静默降级风险摘要：** 删除状态文档回拨后，医护范围、对象访问、
> 本人解析全部回到 users 旧语义；canonical 窗口内的写入残留按 §5.2 R9
> 对账；「删文档当开关」还会绕过变更管理，使回拨动作不可审计。

### 5.2 风险清单

| # | 风险 | 检测手段 | 缓解措施 |
|---|---|---|---|
| R1 | **双形态漏配**：历史 ObjectId/string 引用同 key 双形态；医护归属字段精确匹配在形态上漏配。运行时 `identity_key` 已使两形态等价（`docs/patient-reference-audit.md:56-64`），但 canonical 范围查询按数组精确匹配，形态差异可能漏配。 | 真实库盘点 `ambiguous`/`objectid_form`/`string_form` 计数；切换前对每个域跑双模式结果 diff | G1 盘点门槛；歧义组逐组核实；canonical `assigned_query` 使用迁移后统一形态的患者 ID（迁移保留原 `_id`，形态随原值） |
| R2 | **无账号患者**：canonical 新来源患者无账号、无链接，通知/本人访问/会话不可达。 | 盘点 `users_patients` ↔ `patient_account_links` 覆盖率；切换后监控 `PATIENT_ACCOUNT_UNAVAILABLE` 触发率 | 通知送达经链接解析、无链接跳过（§波次 5）；本人访问严格经 `resolve_self` verified 链接，不猜 ID（`repository.py:114`） |
| R3 | **通知送达缺口**：会话成员/通知接收人保持账号 ID，误把患者实体 ID 当接收人导致通知黑洞。 | 通信合同测试增加 canonical 用例；通知接收人 ID 落库审计比对 `users` 命中率 | 接收人解析只输出账号 ID；无链接患者跳过并记录，不静默丢失败（`communication_service.py:256-261`） |
| R4 | **姓名搜索缺失/语义漂移**：canonical `matching_name_ids` 与 legacy 大小写不敏感语义不一致。 | 双模式同名搜索结果集合比对（含部分匹配、特殊字符转义 `repository.py:171`） | `repository.py:157-171` 已按 legacy 语义对齐 + 姓名索引（:79）；T1 验收用例固化 |
| R5 | **栅栏拆分事务缺陷**：双载体复核只做其一，并发撤权窗口漏检。 | 隔离副本集三种交错场景（§3.3）专项；无事务环境必须拒绝 | §3.3 同事务双复核、失败整体回滚；门闩保留到验收通过 |
| R6 | **external_patient_links 24-hex 硬约束与命名空间混指**：新命名空间 ID 与 users `_id` 同为 24-hex，链接写错集合无类型报错。 | 盘点 `external_patient_links.local_patient_id` 引用落到 users 还是 clinical_patients（对照 `docs/patient-reference-audit.md:46`） | §4 问题 4 决策前置；链接创建路径经 `LegacyPatientRepository.get` 双字面兼容 + 歧义防护（`patient_links.py:98-101`），canonical 后此校验须换域实现 |
| R7 | **第一代 follow_ups 缺 patient_id**：归档只读集合（`docs/patient-reference-audit.md:38,79`）不计入切换，但误纳入聚合/盘点会造成假阳性。 | 盘点报告按集合分列，missing/null 集中在 follow_ups 属预期 | 保持归档只读；聚合与统计的集合清单不含 follow_ups |
| R8 | **people_import 继续写 users 破坏只读约定**：切换后 `users` 只读（README:20-21），若导入路径未切即上线会继续插入。 | 上线前 grep/审计 `users` 写入来源清单（当前唯一：`people_import.py:86`） | 波次 6 决策完成前不启用 canonical 的场景下冻结导入入口，或明确豁免窗口 |
| R9 | **回拨后写入残留**：canonical 窗口内的业务写入不会回流 legacy，回拨再启用会产生双侧数据分叉。 | 每波回滚演练记录窗口内写入清单；对账脚本比对双侧关键集合 | 波次粒度最小化；回拨后按窗口对账（canonical 侧写入导出、legacy 侧补录或放弃重做），重新启用前必须清账 |
| R10 | **域状态文档异常的两种失效形态混淆**：未知模式/版本不匹配/读取失败 → fail-closed 503（`patient_access.py:40-47`）；但**状态文档缺失（被删除）→ 静默回退 legacy**（`repository.py:38-62` 的「无状态文档 = legacy」默认），不产生任何失败信号，canonical 数据仍在却不被消费。误删状态文档不会全站拒服务，而是静默降级。 | 监控 `PATIENT_DOMAIN_STATE_UNAVAILABLE` 告警（只覆盖 fail-closed 形态）；对「流量仍在 users 患者文档上」的读模式做对账监控；状态文档纳入备份与恢复演练范围 | 回拨一律按 §5.1 SOP 显式执行，禁止删文档；状态文档变更加入变更管理；恢复演练（G4）覆盖状态文档重建 |
| R11 | **统计口径割裂**：部分域已切、统计仍读 users，指标错乱。 | 波次 4 前置依赖检查（波次 1–3 完成）；双模式聚合 diff | 常量集中改一处（`analytics_service.py:9` 等）；波次间设依赖门禁 |
| R12 | **迁移工具边界**：工具不能证明不存在未知外部 Mongo 写者（README:64-69）；无数据库恢复函数（README:74-75）。 | 维护窗口端口/进程/服务单元核查清单（README:49-69 的 CLI 检查项） | G5 部署流程排除写者；崩溃/未知提交结果先查证不回灌旧备份（README:75-78） |

---

## 6. 草案声明

**本方案是草案，仅用于评审与排期讨论。** 切换本身未经任何验收：
canonical 模式未在生产启用、迁移未在生产执行、cutover CLI 仍禁用
（`backend/app/patients/README.md:41-43`）。任何人不得依据本文档宣称
患者档案切换完成、迁移完成或业务验收通过。每波执行前须按 §1.2 门槛
逐项留证，执行结果以实际测试与隔离环境验收记录为准。
