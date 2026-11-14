# 历史患者数据迁移与核实方案（T13）

> **状态：草案（未经真实库验证）。** 本方案只描述流程、口径与决策清单，
> **不自动执行任何迁移、归一、清理或删除**。文中所有数字门槛均为建议值，
> 尚未在真实生产库上验证；首次真实库盘点完成后须按实测数据修订。
> 所有代码/文档行号引用基于撰写时的工作区状态（2026-11-14），执行前须复核。
>
> 共同边界约束（`docs/architecture-convergence.md:10`）：现有未提交工作、
> 生产库和已审核历史**不自动迁移或删除**。本方案与该边界一致。

---

## 1. 背景与输入

本方案回答「处理历史数据」任务的第二半：第一半（盘点工具与判定口径）已交付
（`docs/patient-reference-audit.md` + `backend/scripts/patient_reference_audit.py`），
本方案制定其产出事实之后的**核实、归一、缺失处置与迁移执行**流程。

已确认的历史数据线索（均已在代码中核实）：

| # | 线索 | 代码依据 |
|---|---|---|
| L1 | 患者 ID 在业务集合双形态（ObjectId / 24-hex 字符串），运行时经 `identity_key` 等价 | `backend/app/core/patient_identity.py:10-12` |
| L2 | 同 identity key 多文档歧义：运行时 503 fail-closed；迁移侧 `AMBIGUOUS_LEGACY_PATIENT_ID` | `backend/app/core/patient_identity.py:32-40`（无 role 过滤）；`backend/app/patients/migration.py:103-105` |
| L3 | 第一代 `follow_ups` 集合未迁移（FU01 D-4 决策：归档只读）；第一代形状文档缺 `patient_id` 是已知形态 | `backend/scripts/migrate_legacy_collections.py` 头注释（FU01 D-4 段） |
| L4 | `followup_records` 等业务集合部分文档缺 `patient_id`（迁移映射表明确「缺失保持缺失，计数上报」） | 同上，「不映射项」段 |
| L5 | 医护归属字段 `practitioners` / `health_managers` 双形态 + legacy 精确匹配漏配风险 | `backend/app/db/crud_services.py:97-103`（字面精确匹配） |
| L6 | 日常记录真实集合名是带点号的 `patientmanager.daily_records`，患者字段是 `user_id` | `backend/app/api/routers/patient_router.py:92` |
| L7 | `devices.patient_id` 可为 None（历史非患者绑定，设计内）；`rehab_progress.patient_id`；`external_patient_links.local_patient_id` 24-hex 硬约束 | `backend/app/db/indexes.py:50-56`；`backend/app/models/rehabilitation.py:217`；`backend/app/integrations/forms/patient_links.py:34,95-97` |
| L8 | 迁移保留原 `_id`、写 `legacy_user_id`、生成 `legacy_same_document` 审计链接、校验和、幂等语义 | `backend/app/patients/migration.py:66-95,114-128,155-276`；`backend/app/patients/README.md:19-29` |

与第二波段切换（T10 波次计划，`docs/patient-domain-cutover-plan.md`）的关系：
本方案是波次 0 门槛 **G1（盘点干净）** 与 **G2（迁移演练通过）** 的执行方案
（`docs/patient-domain-cutover-plan.md:25-26`）。本方案完成 ≠ 可切换；切换
本身由波次计划管辖。

---

## 2. 阶段一：真实库盘点

### 2.1 运行环境选择（先隔离副本，后真实库）

盘点工具是全集合扫描（`find({})` + 游标分批，`backend/scripts/patient_reference_audit.py:186-202`），
不走索引，在大集合上会产生可感知的读负载。因此：

1. **首选：在隔离实例上对最近一次完整备份的恢复副本运行。**
   工具缺省主机闸门只允许 localhost（`patient_reference_audit.py:98,352-359`），
   恢复副本跑在本机恰好契合闸门，也无需 `--allow-remote`。若副本数据滞后于
   生产，须在报告中记录快照时间点。
2. **备选：生产库低峰窗口直读。** 只读保证成立（代码路径仅 find/to_list，
   无 insert/update/delete/create_index/drop，测试有写调用即失败的断言，
   见 `docs/patient-reference-audit.md:30-31`），但必须：
   - 明确记录执行窗口与操作人；
   - 大集合调低 `--batch-size`（默认 1000，可降为 500）观察副本延迟；
   - 远程实例须显式 `--allow-remote`，该 flag 本身记入盘点留痕。

**无论哪种方式，工具本身绝不写库；但"对生产库运行"这个动作本身仍须
按第 8 节决策清单 D-12 获得授权。**

### 2.2 执行步骤与输出留存

```bash
cd backend
MONGODB_AUDIT_URI="mongodb://<隔离实例>:27017" \
    .venv/bin/python -m scripts.patient_reference_audit \
    --db <库名> --max-examples 50 > audit-<日期>-<环境>.json
```

- `--max-examples` 建议从默认 20 提到 50：样本是核实阶段（§3）的直接输入，
  样本不足会导致二次跑库。若 `examples_truncated: true`，核实清单须以
  全量导出补齐（样本只是入口，不是全集）。
- **留存要求**：JSON 报告按 `audit-<日期>-<环境>.json` 命名归档，与
  stderr 摘要一起作为波次 0 G1 门槛证据；同一环境至少留两次（处置前 /
  处置后）用于对比。报告含生成时间与库名（`patient_reference_audit.py:314-316`），
  可自证环境。
- 盘点范围以工具内置清单为准（16 个集合/字段 + users 患者子集，
  `patient_reference_audit.py:76-93`），与 `docs/patient-reference-audit.md:35-50`
  一致，不在本方案中另行扩列；若执行时发现新业务集合持有患者引用，
  先补工具清单与测试，再重跑盘点，不得口头补数。

### 2.3 门槛判定（建议值，待实测修订）

**"盘点干净"（G1）建议按以下口径判定**（均为建议值，首次实测后修订）：

| 指标 | 通过条件 |
|---|---|
| `users_patients.duplicate_identity_groups` | **= 0 组**。>0 时逐组核实并处置（合并/禁用/删除，见 §3.2 与决策项 D-1）后复跑至 0 |
| 各业务集合 `ambiguous` | **= 0**。歧义是 L2 中运行时 503 的直接来源，不接受豁免带病切换 |
| 各业务集合 `dangling` | **= 0，或逐条核实清单全部有书面结论**（三类结论：脏数据→清理；已删账号→书面豁免并留档；形态问题→归一策略覆盖）。逐条清单格式见 §3.3 |
| `follow_ups` 的 missing/null | 已知历史形态（L3），**预期内不算失败**，但须在报告中显式引用 FU01 D-4 决策作为豁免依据 |
| 其余集合（`followup_records` 等）missing/null | = 0，或逐条核实（§5.2） |
| `devices` 的 null | 设计内（L7），列清单确认数量级，按 D-7 决策追认豁免 |
| `other_form` 引用 | 逐条核实：非 24-hex 的自由字符串 ID 无法与 `users` 可靠关联，多数会落 dangling，不允许静默豁免 |
| 归属字段（practitioners/health_managers）dangling | = 0 或逐条核实（§4.3、D-8） |
| 双形态计数（objectid_form/string_form） | **不要求归零**：`identity_key` 使两形态运行时等价，形态本身不是故障（`docs/patient-reference-audit.md:76-78`）。计数留档作为归一决策（D-3）输入 |

注意一个**必须人工把关的口径差**：盘点的歧义判定无 role 过滤
（`patient_identity.py:32-40`），而迁移自身的 `AMBIGUOUS_LEGACY_PATIENT_ID`
门（`migration.py:103-105`）只对 `role:"patient"` 文档去重。若某 key 同时命中
一个患者文档和一个非患者文档（如 doctor），迁移可能通过而运行时适配器
仍 503。因此 **`duplicate_identity_groups` 必须以"对全部 users 无 role 过滤
= 0"为准**，不能以迁移工具不报错代替 G1。

---

## 3. 阶段二：逐条核实

### 3.1 核实对象

按盘点报告分四类建清单：

1. **歧义组**（`duplicate_identity_groups` + 各集合 `ambiguous_examples`）：
   每组列出 key 与全部 `user_ids`。
2. **悬空引用**（各集合 `dangling_examples`，样本截断时全量导出）：
   按"集合 × key"去重。
3. **缺失引用**（`missing`/`null`，`follow_ups` 与 `devices` 除外）。
4. **归属字段异常**（悬空条目、`resolved_roles` 与预期 role 不符的条目）。

### 3.2 核实流程

| 环节 | 要求 |
|---|---|
| **谁确认** | 方案不指定具体人名。最小角色配置：业务负责人（患者账号归属与合并裁定）、临床负责人（涉及诊疗记录归属时）、平台工程（执行核实查询、提供技术证据）。每条结论须同时有业务侧签字人与技术侧执行人；涉及临床数据归属的条目须临床负责人加签 |
| **依据什么凭证** | 逐条核实必须给出可指认的证据，不接受"看起来没问题"。可用凭证：① `users` 文档原始字段（`createdAt`/`updatedAt`、`source_project_id`、登录与 is_active 状态）；② 引用方业务文档上下文（该悬空引用所在业务记录的业务含义与时间）；③ 外部系统对照（113.44 侧同一来源患者身份）；④ 历史操作/审计记录（如有）。技术侧负责把每条 key 的上述证据查询结果附到清单上 |
| **结论记录在哪** | 建立**核实台账**（建议 `docs/patient-data-remediation-ledger.md`，由核实阶段新建并逐条追加；本方案不预建）。每条记录：集合、identity key、引用样本、分类（歧义/悬空/缺失）、结论（处置动作或豁免）、凭证引用、业务签字人、技术执行人、日期。台账与两次盘点 JSON 一起归档为 G1 证据 |
| **闭环** | 所有处置类结论执行后**复跑盘点**，对应指标归零才算闭环；豁免类结论在台账留档并在切换证据中引用 |

### 3.3 必须业务/临床侧输入的问题

核实过程中以下问题技术侧无法自答，须业务/临床明确（并入 §7 决策清单
D-1、D-2、D-5、D-9）：

- 同 key 多文档组里哪个是"真"账号、哪个是误建？合并方向与合并后旧 ID
  的引用是否重写？
- 已删账号造成的悬空引用：业务上接受"记录仍在、患者不可达"吗？
- `followup_records` 缺 `patient_id` 的文档，能否从业务上下文（creator、
  时间、内容）可靠推断归属？推断本身是否被业务接受（详见 §5.2）？
- devices 历史非患者绑定清单数量级是否与业务记忆一致？

---

## 4. 归一策略

### 4.1 双形态引用：运行时等价是现状，物理归一是可选项

现状事实：

- 运行时读取路径已双形态等价：`identity_key`（`patient_identity.py:10-12`）、
  `load_identity_groups` 的双形态 `$in`（:15-22）、共享读取适配器的双字面
  兼容（`backend/app/integrations/forms/patient_links.py:98-101` 注释）、
  canonical `assigned_query` 双形态 `$in`（`backend/app/patients/repository.py:92-98`）、
  过程质控聚合的双键 `$expr` 匹配（`backend/app/services/quality_process_queries.py:76-79`）。
- 迁移**不重写任何业务引用**："Existing business references need no ID rewrite"
  （`backend/app/patients/README.md:20-21`）；迁移只保留原 `_id` 并派生
  `patient_id = str(_id)`（`migration.py:80-81`）。

因此：**归一不是迁移的前置条件**，迁移窗口内不做任何业务集合的字段重写。
物理归一（把业务集合引用统一改写为 canonical 24-hex 字符串形态）是否做、
何时做，取决于是否存在**按 BSON 字面相等匹配且无法双键化的路径**：

- 目前已知的候选触发点是波次 3/4 的跨域聚合：过程质控 `$lookup` 切换
  `PATIENT_USERS_COLLECTION` 常量（`quality_process_queries.py:11`）、统计
  常量（`backend/app/services/analytics_service.py:9` 等）。过程质控管线
  已双键化；其余常量路径切换时须逐一确认其对 ObjectId 形态的容忍度，
  不容忍处优先改查询（双键化），改不动再考虑数据侧归一。
- 结论：**归一窗口放在"双读窗口"（波次 1 切换后、各写路径波次进行中），
  按集合逐个决策，而不是迁移前一把梭**。迁移前批量重写会同时违反
  "迁移不重写引用"的既定设计（README:20-21）和"生产库不自动迁移"
  边界（`architecture-convergence.md:10`）。

### 4.2 与 T10 波次的衔接点

| 衔接点 | 本方案动作 | 波次计划动作 |
|---|---|---|
| 波次 0 前置 | 完成 §2 盘点 + §3 核实，产出 G1 证据 | `patient-domain-cutover-plan.md:25` G1 门槛核验 |
| 波次 0 | 完成本方案 §6 的隔离实例迁移演练，产出 G2 证据（manifest 比对一致） | `:26` G2 门槛核验 |
| 波次 1（读取面） | 无数据动作；`assigned_query` 已双形态 `$in`，双形态不阻塞读取切换 | 读取面切 canonical |
| 波次 3/4（聚合/统计） | 按 §4.1 输出各常量路径的双形态容忍度核查结论（D-3 的输入） | 替换患者集合常量；若某路径不容忍双形态且改不动查询，则该路径触发数据侧归一（须业务确认后单独执行） |
| 波次 6（新患者创建） | 本方案不管辖；`external_patient_links` 命名空间混指等 7 个决策点见 `patient-domain-cutover-plan.md:241-276` §4 | 业务决策波 |

### 4.3 医护归属字段漏配修复

问题事实：legacy 路径 `find_by_doctors` / `find_by_health_manager` 用
字面精确匹配（`crud_services.py:97-103`，`{"practitioners": doctor_id, ...}`）。
患者文档归属数组若存的是 ObjectId 形态、而调用方传 24-hex 字符串（或反之），
精确匹配**静默漏配**——患者从医生列表消失，无报错。canonical
`assigned_query`（`repository.py:92-98`）已双形态 `$in`，此漏配只在 legacy
读取路径与切换前的现状查询中存在。

修复方式两选（决策项 D-4）：

- **查询侧修复（推荐）**：把 legacy 精确匹配改为 `identity_candidates`
  双形态 `$in`（与 `patient_identity.py:15-22` 同口径），一行改动、不碰数据、
  与运行时其余路径口径一致。属于代码修复，走正常开发交付，不属于数据迁移。
- **数据侧归一**：把 `users` 患者文档的 `practitioners`/`health_managers`
  条目统一改写为 canonical 字符串。**只在迁移窗口内、由迁移事务一并完成
  才被允许**（users 只读约定，README:20-21）——但当前 `project_legacy_patient`
  （`migration.py:66-95`）**原样保留**归属字段，不归一；要改须先改迁移代码
  并重做隔离演练。成本高、收益与查询侧修复重叠，除非波次 3/4 查出存在
  无法查询侧化解的路径，否则不推荐。

在数据侧归一被采纳之前，`other_form` 的归属条目（非 hex 字符串的医护 ID）
无法被任何双形态 `$in` 命中，只能逐条核实（§2.3 表中归属字段行）。

---

## 5. 缺失与孤儿处置

### 5.1 第一代 `follow_ups`（缺 patient_id 的主体）

**现状决策已存在**：FU01 D-4（2026-11-09）判定归档只读、不迁移
（`backend/scripts/migrate_legacy_collections.py` 头注释 FU01 D-4 段；
`docs/patient-reference-audit.md:38,79-80`）。本方案不重开该决策，只要求：

- 盘点报告中 `follow_ups` 段的 missing 计数作为豁免依据显式引用；
- 聚合与统计的集合清单不含 `follow_ups`（与 `patient-domain-cutover-plan.md:289` R7 一致）；
- 归档副本（`archive_follow_ups`，若已执行 `--archive`）与原集合的关系留档。

### 5.2 `followup_records`（及类似业务集合）缺 patient_id 的文档

迁移映射表对此类文档**明确不映射 patient_id、缺失保持缺失、计数上报**
（`migrate_legacy_collections.py` 头注释"不映射项"段）。处置选项（决策项 D-5）：

- **选项 A：保持缺失 + 质量管线标记。** 过程质控聚合已把 missing/null
  归为 `missing` 参考口径（`quality_process_queries.py:77,81` 附近
  `_qc_patient_reference` 判定），文档保留在业务集合但被质控标记，
  不参与患者归属统计。零数据风险；代价是这些随访记录永久不可归属。
- **选项 B：补挂。** 对每条缺失文档，依 §3.2 凭证流程从业务上下文推断
  归属并回写 `patient_id`。代价：推断即风险，回写是对业务集合的历史数据
  写操作，须逐条留证、业务签字、隔离演练后执行；无法可靠推断的文档
  退回选项 A。

**默认建议 A**；只有业务明确要求恢复这批记录的归属、且凭证可逐条指认时
才走 B。无论 A/B，均须先把"缺 patient_id 文档清单"从盘点 missing 计数
展开为逐条清单（样本截断时全量导出）。

### 5.3 `devices.patient_id` 为 None 的绑定

设计内（L7）：设备可无患者绑定，管理员只读盘点历史非患者绑定、未自动
删除或改绑（`docs/architecture-convergence.md:33`）。处置（D-7）：
盘点列清单确认数量级；保留原状（null 继续表示"未绑定患者"），除非业务
明确某批设备应绑定/应废弃——后者属于设备管理业务流程，不属于本数据方案。

### 5.4 孤儿引用（dangling）与悬空归属条目

- **悬空业务引用**（指向不存在账号）：处置三分法——脏数据清理 / 已删账号
  书面豁免 / 形态问题并入归一（§2.3）。清理动作本身是对业务集合的写操作，
  逐条留证 + 业务签字 + 隔离演练，见 D-2。
- **悬空归属条目**（`practitioners`/`health_managers` 指向不存在医护）：
  同三分法（D-8）。注意悬空医护条目若同时是 `other_form`，双形态查询修复
  也救不回，只能逐条核实。
- **原则**：孤儿引用不阻塞迁移（迁移只搬 `users` 患者，不校验业务集合引用），
  但 G1 门槛要求逐条有结论；"无结论即切换"不被允许。

---

## 6. 迁移执行手册（基于 migration.py 真实语义）

### 6.1 迁移语义事实（以 `backend/app/patients/migration.py` 为准）

- **范围**：只迁移 `users` 中 `role:"patient"` 文档（`migration.py:99`）；
  保留原 `_id`，派生 `patient_id`/`legacy_user_id` = `str(_id)`，按 `is_active`
  映射 `status`（`migration.py:80-83`）；坏数据 fail-closed
  （`INVALID_LEGACY_PATIENT*` 系列，:66-95）。
- **写入**：同一事务内写 `clinical_patients`、`patient_account_links`
  （`legacy_same_document` 来源，verified/disabled 随 is_active，含
  reviewer/evidence/at 审计，:114-128）、`patient_domain_state` 单例
  （migrating → canonical，:244-264）。事务 read_concern snapshot /
  write_concern majority（:227-229）。**`users` 全程只读**
  （`README.md:20-21`；`users_modified: False`，`migration.py:275`）。
- **歧义 fail-closed**：patient 范围内 `patient_id` 不唯一即
  `AMBIGUOUS_LEGACY_PATIENT_ID`（:103-105）——注意口径差，见 §2.3 末段。
- **校验和**：inspect 产出 legacy/projection/links 三个 SHA256（:170-176）；
  apply 前后各重指纹比对（:209-211, :237-239, :252-259），任何漂移即
  `PATIENT_MIGRATION_BASELINE_CHANGED` 等错误中止。
- **幂等**：state 已 canonical 时直接返回 `verified_noop`
  （:203-204）；不存在"刷新/重放已迁移域"的路径
  （`README.md:79`）。
- **备份与日志**：私有快照目录 0700/文件 0600，写 legacy 患者账号 BSON
  快照 + manifest（:212-217）；不可变 journal 三件套
  `00-prepared / 01-commit-attempted / 02-committed`（:218-273）。
  快照含完整账号文档即含敏感信息，不替代数据库备份（`README.md:71-74`）。
- **不可逆**：**没有数据库恢复函数**（`README.md:74-75`；
  `database_restore_supported: False`，`migration.py:221`）。提交前失败靠
  事务回滚；提交后数据层面回滚只能靠完整数据库备份恢复（人工，工具外）。
- **合成失败注入**：`fail_at=before_transaction/after_insert/before_commit`
  （:225-226,250-251,265-266）仅用于演练，生产执行不得传。

### 6.2 前置条件

1. G1 证据齐备（§2-§3 完成）。
2. **G4 备份可恢复**：完整数据库备份 + 独立恢复演练成功
   （`patient-domain-cutover-plan.md:28`）。这是提交后数据回滚的**唯一**手段。
3. G5 写者排除：应用停机走 `stop.sh`；应用写者、后台调度、外部直连工具
   由部署流程排除（CLI 会核查 managed unit MainPID0、无存活项目进程、
   应用端口无监听，`backend/scripts/manage_clinical_patients.py` +
   `README.md:61-69`）。CLI 核查**不能证明不存在未知外部 Mongo 写者**
   （`README.md:64-69`），须以部署流程兜底并在窗口记录中留证。
4. 副本集环境（`migration.py:205-206`）；standalone 事务不可用，直接拒绝。
5. **CLI cutover 当前禁用**（`manage_clinical_patients.py:90-93`）。启用
   cutover 属于波次计划的集成验收结论，不在本方案授权范围内；本方案
   的 §6.3 仅描述"未来解锁后"的执行步骤。
6. reviewer 与 evidence_reference 已按 D-10 确定（`migration.py:199-200`
   强制非空，写入 state 与链接审计）。

### 6.3 执行步骤

1. **inspect**（只读）：
   `DEBUG=false backend/.venv/bin/python backend/scripts/manage_clinical_patients.py --manifest-output <私有路径>/inspection.json`
   —— 产出 manifest（profile、库名、副本集、三个 SHA256、计数）。
   `UNEXPLAINED_CLINICAL_PATIENT_DATA` / `UNEXPLAINED_PATIENT_ACCOUNT_LINK_DATA`
   任一报错说明目标库已有 canonical 侧数据且无状态文档，先查原因再继续
   （`migration.py:162-167`）。
2. **人工比对 manifest**：`legacy_count` 与盘点报告 `users_patients.total_patients`
   应一致；`legacy_count` 为 0 时 `projected` 为空、迁移只写 state（合法但
   说明源库无患者，须先解释）。
3. **apply**：按 `README.md:49-59` 的完整参数执行（expected-manifest、
   expected-database-name、backup-directory、reviewer、evidence-reference、
   managed-unit、端口、`--maintenance-confirmed`）。
   apply 内部顺序：guard 核查 → inspect 复核 → manifest 与实时指纹双比对
   → 私有快照 → 索引创建 → 事务（in-tx 再 guard + 空集合复核 + 指纹复核
   + 插入 + 写后三项指纹校验 + state 置 canonical）→ backup 校验 →
   journal 提交收尾（`migration.py:191-276`）。
4. **留存**：manifest、备份目录、三个 journal 文件全部作为 G2/迁移证据归档。

### 6.4 失败恢复

| 失败点 | 表现 | 处置 |
|---|---|---|
| 事务内任何一步失败（含 `after_insert` 注入） | 事务整体回滚，`clinical_patients`/links/state 无残留（`README.md:75-76`） | 排查报错（baseline 漂移/歧义/投影校验等），修正后从步骤 1 重跑；journal 留在 `00-prepared` |
| `before_commit` 注入或**提交结果未知**（崩溃/网络中断） | journal 已写 `01-commit-attempted`（`committed: None, outcome: commit_outcome_unknown`） | **先查证、不回灌旧备份**（`README.md:75-78`）：读 state 单例实际状态——canonical 即已提交（按已迁移处理，走 §6.5）；无 state/仍 migrating 则未生效（按事务回滚处理，重跑）；无法判定时人工核查三个集合内容，禁止盲目恢复备份 |
| 提交后发现问题 | 数据已 canonical，工具不可逆（§6.1） | 数据层只能走 G4 的完整备份恢复（人工决策，见 D-11）；域层可先按波次计划"域开关回拨"恢复 legacy 语义（canonical 侧该窗口写入按 R9 对账，`patient-domain-cutover-plan.md:291`） |

### 6.5 执行后验证

1. **state 单例**：`mode=canonical`、`schema_version=1`，
   `migrated_count`/`legacy_sha256`/`projection_sha256`/`account_links_created`/
   `legacy_links_sha256` 与 manifest 逐一相等（`migration.py:260-264` 写入）。
2. **journal 对账**：`02-committed.json` 与 manifest 一致。
3. **复跑盘点**（§2 同环境同参数）：报告应与迁移前**完全一致**——
   迁移不改 `users`（`users_modified: False`），业务集合引用一字未动，
   所以 dangling/ambiguous/形态计数不变。**盘点数字发生变化 = 迁移窗口内
   有其他写者动了库**，立即按异常处置。
4. **canonical 侧抽验**：`inspect_migration` 的 `clinical_count` ==
   `legacy_count`；抽样核对若干患者的 `clinical_patients.patient_id` ==
   原 `users._id` 字符串、`patient_account_links` 对应链接
   `source=legacy_same_document`、inactive 账号对应 `status=disabled` 链接。
5. 业务抽查：迁移后的库上按波次计划波次 1 验证清单跑医护列表、本人、
   随访范围、设备读取冒烟（`patient-domain-cutover-plan.md:74-80`）。

### 6.6 回滚边界（结论）

- **提交前**：可回滚——事务回滚即恢复原状，无副作用。
- **提交后数据层**：**不可由迁移工具回滚**。唯一途径是 G4 的完整备份恢复
  （人工、部署流程管辖），恢复决策须业务确认（D-11），且恢复前必须先
  按 §6.4 "提交结果未知"分支查证实际状态。
- **提交后行为层**：域开关回拨到 legacy 是波次计划的既定回滚方式
  （`patient-domain-cutover-plan.md:36-41`），只改变读取/授权路径，不改数据；
  回拨窗口内 canonical 侧写入的对账（R9）不在本方案范围。

---

## 7. 决策清单（需业务确认项汇总）

本方案不自动执行任何动作；以下 12 项须有书面结论后对应阶段才可推进。

| # | 决策项 | 决策内容 | 阻塞点 |
|---|---|---|---|
| D-1 | 同 key 多文档（歧义）处置 | 逐组裁定合并/禁用/删除方向；合并后旧 ID 引用是否重写 | G1 闭环；波次 0 |
| D-2 | 悬空业务引用处置 | 逐条：清理 / 书面豁免（已删账号）/ 并入归一；清理须授权 | G1 闭环 |
| D-3 | 双形态引用是否物理归一、何时归一 | 默认不做迁移前归一；波次 3/4 按常量路径双形态容忍度逐集合决定 | 波次 3/4 前置核查 |
| D-4 | 医护归属漏配修复方式 | 查询侧双形态 `$in`（推荐）vs 数据侧归一（须改迁移代码+重演练） | 波次 1 前 |
| D-5 | `followup_records` 缺 patient_id 文档处置 | 保持缺失+质控标记（默认）vs 逐条补挂（须凭证+签字） | §5.2；盘点后 |
| D-6 | 缺失处置的凭证标准 | 补挂/清理类动作接受什么证据（113.44 对照、业务上下文等） | 与 D-2/D-5 配套 |
| D-7 | devices None 绑定追认 | 确认保留设计内语义，或列明应绑定/应废弃批次 | G1 闭环 |
| D-8 | 悬空归属条目处置 | 清理 / 豁免 / 归一；other_form 条目逐条 | G1 闭环 |
| D-9 | 已删账号悬空引用的业务口径 | "记录在、患者不可达"是否被业务接受并留档 | 与 D-2 配套 |
| D-10 | 迁移 reviewer / evidence_reference 签署人 | 谁有资格签（`migration.py:199-200` 强制），evidence 指向什么材料 | 迁移 apply 前 |
| D-11 | 提交后数据回滚的授权路径 | 完整备份恢复的触发条件与批准人（工具不可逆，见 §6.6） | 迁移 apply 前 |
| D-12 | 生产库直读盘点的授权 | 若不走隔离副本而直读生产库，窗口与操作人须授权留证 | §2.1；首次盘点前 |

另：波次 6 的新患者创建路径 7 项决策（含 `external_patient_links` 命名空间
混指）在 `docs/patient-domain-cutover-plan.md:241-276`，不重复列入本清单。

## 8. 边界声明

1. **本方案不自动执行任何迁移、归一、清理、删除**。所有写操作（补挂、
   清理、归一、迁移 apply）均须按 §7 对应决策项取得业务确认、在隔离实例
   演练后、按迁移脚本既有约束（`migrate_legacy_collections.py` 头注释
   "任何真实迁移/归档执行前必须业务确认"）执行。
2. **本方案未经真实库验证**。§2.3 的数字门槛、§5 的处置选项均为基于代码
   与既有决策的建议值；首次真实库盘点完成后须按实测修订并重审本方案。
3. 生产库与已审核历史不自动迁移或删除（`docs/architecture-convergence.md:10`）。
4. 切换本身（域开关、波次推进）由 `docs/patient-domain-cutover-plan.md`
   管辖；本方案只覆盖 G1/G2 门槛的数据侧工作。本方案完成不构成任何
   迁移完成、切换完成或业务验收完成的宣称。
