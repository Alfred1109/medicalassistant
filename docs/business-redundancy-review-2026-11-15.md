# 业务架构冗余判定（2026-11-15）

配套文档：`redundancy-review-2026-11-15.md`（技术侧冗余审查与四批次路线）、`architecture-convergence.md`（架构收敛工作记录）。

本文件回答一个问题：**业务层面哪些是重复建设、哪些是功能空洞、哪些看着像重复但其实分层不同**。结论按四类判定，每条都带可核对的代码位置。

## 判定口径

| 判定 | 含义 | 处置 |
|---|---|---|
| **合并** | 同一业务事实有多处存储/实现，迟早发散 | 收敛到单一事实源，其余改为读取或视图 |
| **补齐** | 不是冗余，是功能空洞（点得进去、永远是空的） | 按真实语义实现，不留空壳 |
| **保留** | 看似重复实为分层不同，合并会丢信息 | 明确登记为非冗余，不再反复讨论 |
| **下线** | 无消费方、无实现价值 | 删除或明确标注为预留 |

涉及临床口径的分歧（随访完成率、ICF 指标关联等）：**一律参数化 + 保守默认 + 标注"待临床确认"**，不作为阻塞项等拍板。技术上不成立的才停下来问。

---

## 一、数据落点冗余

### 1.1 生命体征三套存储（合并）

同一类生理数据落在三个地方：

| 落点 | 写入方 | 读方 |
|---|---|---|
| `health_data` 集合 | [health_record_service.py:365,478,535](backend/app/services/health_record_service.py) | 医护健康档案、预警手工录入 |
| `device_data` 集合 | [device_service.py:294](backend/app/services/device_service.py)（手工）、[device_ingestion_service.py:319](backend/app/services/device_ingestion_service.py)（设备网关） | 仅 `device_analysis_service` 三个分析入口（:83,:266,:842） |
| `health_records` 内嵌 `vital_signs` | [core/dependencies.py:215](backend/app/core/dependencies.py) 置默认空数组 | [doctor_router.py:114](backend/app/api/routers/doctor_router.py) 投影、已死的 multimodal_service |

**后果（已核实）**：设备采集的血压进不了医护时间线（`medical_timelines` 由 health_record_service 与 followup_service 写，设备侧不写）；患者手录的血压进不了设备分析（`device_analysis_service` 只读 `device_data`）。

**判定：合并**。以 `health_data` 为生命体征事实源，设备数据经网关落同一集合（保留来源标记 `source=device` 与设备 id），`device_data` 降级为设备原始遥测留档；内嵌 `vital_signs` 改为读取投影，不再单独存。

**注意**：这是有历史数据面的改动——上线前需先跑一次存量盘点（`health_data` / `device_data` / 内嵌 `vital_signs` 三处的血压、血糖、心率条目数与重叠量），重叠条目需要去重口径。盘点工具已交付：`backend/scripts/vitals_storage_audit.py`（只读），生产执行方式见 `external-validation-checklist.md` A5。

### 1.2 `medical_timelines` 陈旧物化（合并）

[health_record_service.py:75,372,485,542](backend/app/services/health_record_service.py) 与 [followup_service.py:550,782,833](backend/app/services/followup_service.py) 往 `medical_timelines` 写副本，时间线是**物化出来的**，采集侧不写，因此必然落后于事实源。

**判定：合并** —— 时间线改为按事实源实时聚合（健康数据 + 随访 + 评估），不再维护副本集合。已有历史条目保留可读（只读历史视图），新数据不再双写。

### 1.3 `health_metrics` 孤儿集合（下线或补写）

[ dashboard_service.py:35](backend/app/services/dashboard_service.py) 读 `db.health_metrics`，全仓**无任何写入方**。患者看板拿到的永远是空数组。

**判定：合并到 1.1 的统一落点**，删除该读方；集合本身留待运维清理（不在应用代码里 drop 生产集合）。

### 1.4 `medical_timelines` 与 `health_records` 的事件双写（合并）

同一次随访/健康记录变更会同时写业务记录和 timeline 副本，两者可由同一事件推导。见 1.2，一并处理。

---

## 二、触达与流程冗余

### 2.1 预警触达空洞（补齐 · 最高优先）

阈值预警与 ICF 指标预警**只写 `alerts` 集合，不产生任何通知**：[health_alert_service.py:526](backend/app/services/health_alert_service.py) 的 `create_alert` 仅 insert；[icf_service.py:596-632](backend/app/services/icf_service.py) 计算越界后调用它，且注释写着"复用既有通知链路"——**该注释与事实不符，既有问题不存在**。

结果：系统里出现危急预警，医护收不到任何信号。

**判定：补齐**。预警创建时经统一通知服务向该患者责任医护产出通知（责任归属复用 `core/patient_access.py` 既有能力，不另写判定；无责任医护时跳过通知但不阻断预警创建）。

→ Wave 2 任务 A

### 2.2 两条通知生产链（合并）

[followup_reminder_service.py:218-249](backend/app/services/followup_reminder_service.py) 直接 `db.notifications.insert_one` 手搓通知文档，再用函数内延迟 import 手推 WS，绕开了 [notification_service.py](backend/app/services/notification_service.py)（该服务已内置 WS 推送与可选邮件）。两条链的字段与投递语义分叉。

**判定：合并** —— 单一生产者 `NotificationService.create_notification`。

→ Wave 2 任务 A

### 2.3 `alerts` 与 `quality_issues` 两套同构状态机（合并）

两者状态流转形状相同，但 `alerts` 侧没有版本号、幂等键与复核保护，且 [device_analysis_service.py](backend/app/services/device_analysis_service.py) 另有一套阈值判定。

**判定：合并** —— 复用已建的 `review_state_machine.py` 扩展到 alerts；阈值判定收敛到一处（设备侧与手工侧共用同一规则入口）。

→ Wave 3

---

## 三、指标与口径冗余

### 3.1 三套指标体系（保留 · 明确非冗余）

临床数值指标、ICF 功能指标、过程质控指标分属**不同层次**：前者是测量值，中者是功能水平，后者是过程合规。合并会丢维度。

**判定：保留**。唯一问题是 `icf_code` 关联目前只是展示用的字符串，**不参与任何计算**——这不是冗余，是尚未接线的功能；接线与否等临床口径定，不在本轮强接。

### 3.2 随访完成率两套状态枚举（合并 · 口径参数化）

[quality_process_queries.py:5](backend/app/services/quality_process_queries.py) 定义 `FOLLOWUP_STATUSES = ("pending_schedule","scheduled","awaiting_fill","in_review",...)`；ICF 侧把 `in_review` 计入失败分母，质控侧把 `pending` 节点当未完成。两个口径对同一批随访给出不同完成率。

**判定：合并** —— 枚举定义归一（一处定义状态全集与语义），完成率公式参数化：默认取保守口径（未终态即未完成），并把口径选择暴露为配置项、页面上标注"待临床确认"。

→ Wave 3

### 3.3 CSV 导出器两套 + 公式注入防护不一致（合并 · 安全项）

[quality_monitoring_service.py:42-48](backend/app/services/quality_monitoring_service.py) 的导出器有 `= + - @ \t \r \n` 前缀守卫；[clinical/workspace.py:867-877](backend/app/clinical/workspace.py) 的 `_csv` 只处理逗号/引号/换行转义，**没有公式注入防护**——`indicators.csv` 里的临床数值若以 `=` 开头，用 Excel 打开会执行公式。

**判定：合并** —— 统一导出器，前缀守卫为共用实现（守卫规则以质量侧为准）。

→ Wave 3（本轮我直接改，不占并行任务）

### 3.4 `report-schedules` 伪实现（下线）

[report_scheduler_service.py](backend/app/services/report_scheduler_service.py) 的"PDF 报表"实际生成 JSON、"Excel 报表"实际生成 CSV，且无前端消费方。

**判定：下线**（登记见 `t53-dead-code-disposal-report-scheduler.md`）。

→ Wave 2 任务 E

---

## 四、入口与页面冗余

### 4.1 医生与健管师共用页面组件，目录名误导（合并命名）

[frontend/src/routes.tsx:311-355](frontend/src/routes.tsx) 里医生与健康管理师两条路由**用的是同一批页面组件**（患者管理、健康档案、随访、临床工作台、ICF、设备、数据监测、沟通、统计、知情同意），只有 URL 前缀与角色守卫不同。

`pages/HealthManager/` 目录里则是混装：`HealthManagerDashboard` / `HealthDataTimelinePage` / `HealthThresholdPage` 是健管师专属页（合理），而 `HealthRecords.tsx` 是零引用的重复件（见 4.2）。目录名让人以为健管师有整套独立界面，实际只多两三个专属页。

**判定：合并** —— 删掉重复件后，把剩余专属页集中到能说清含义的位置（保留 `pages/HealthManager/` 亦可，重点是目录里不再有共享组件的副本）。命名改动会波及 import，按低风险排期。

→ Wave 2 任务 D

### 4.2 前端死代码两处（下线）

[pages/HealthManager/HealthRecords.tsx](frontend/src/pages/HealthManager/HealthRecords.tsx)（919 行）与 [pages/Common/DataMonitoring.tsx](frontend/src/pages/Common/DataMonitoring.tsx)（629 行）**零引用**——路由用的是 `pages/Doctor/` 下的同名组件（见 `frontend/src/routes.tsx:55,57`）。

**判定：下线**。

→ Wave 2 任务 D

### 4.3 健管师「数据统计」是空壳（补齐）

菜单对 health_manager 显示"数据统计"，但 [health_manager_router.py:120-131](backend/app/api/routers/health_manager_router.py) 判断角色后直接 `return {}`。医生侧同名端点已有真实聚合实现（[doctor_router.py:251](backend/app/api/routers/doctor_router.py) 起，含患者数、方案数与状态分布、本月完成数，并显式标记 `implemented`）。

**判定：补齐** —— 健管师侧实现同口径真实聚合，无数据时如实为 0；两端口径可复用则抽共享实现。

→ Wave 2 任务 D

### 4.4 菜单与路由双源、请求通道四路、类型与日期多份（合并）

[frontend/src/routes.tsx](frontend/src/routes.tsx) 与菜单配置各维护一份，靠人工同步；请求通道并存四路；错误提取多套（已部分收口到 `services/patientErrors.ts`）；日期格式化 20+ 份；ICF 类型双份。

**判定：合并** —— 菜单与路由单源化（先补一致性快照测试再改实现），其余按批收口。

→ Wave 2 任务 D（菜单/路由/类型/日期/通道），Wave 3（共享 hooks 迁移）

### 4.5 AI 四条调用路径、配置三处来源（合并）

Agent、plan-gen、exercise-recommendation、vision-extraction 四条路径，配置散在 `LLM_API_*`、`VISION_API_*` 与库内 prompt 三处，调用风格两种（`llm_transport` 与直接调 OpenAI SDK）。

**判定：合并** —— 配置收口到一处（保留各路径的专有参数），调用统一走同一 transport。

→ Wave 3

### 4.6 已死的三块 AI 服务（下线）

`agent_optimized_service.py` + `api/endpoints/agent_optimized.py`、`multimodal_service.py`、`prediction_service.py` 无有效消费方。

**判定：下线**（`agent_optimized` 是否为预留特性需确认，见任务 E 报告）。

→ Wave 2 任务 E

---

## 五、明确非冗余（登记为保留，不再反复讨论）

- **三套指标体系**（3.1）：层次不同，合并即丢信息。
- **双审计体系**（`audit_logs` 访问审计 vs 链接内嵌业务审计）：后者是承重的授权证据。
- **医生/健管师共用页面组件**（4.1）：组件不冗余，冗余的是目录命名。
- **`device_data` 原始遥测留档**（1.1）：与 `health_data` 的"事实源"角色不同——收敛后它不再存临床事实，但保留设备原始读数是设备证据链需要，不是重复建设。
- **`core/` 下的 access 家族**：本仓做得最好的部分。

---

## 六、排期

| 波次 | 任务 | 覆盖条目 |
|---|---|---|
| Wave 2（在途） | A 通知链路统一与预警触达 | 2.1、2.2 |
| Wave 2（在途） | B 域分派内核化与分支标签 | 技术侧，不涉业务判定 |
| Wave 2（在途） | C 依赖方向与主入口收敛 | 技术侧 |
| Wave 2（在途） | D 前端收敛与健管师统计 | 4.1、4.2、4.3、4.4（部分） |
| Wave 2（在途） | E 三设施基座与死代码处置 | 3.4、4.6 |
| Wave 3 | 生命体征单一事实源 | 1.1、1.2、1.3、1.4 |
| Wave 3 | 指标口径与导出器统一 | 3.2、3.3 |
| Wave 3 | 预警状态机与阈值判定收敛 | 2.3 |
| Wave 3 | AI 配置与 transport 收口、共享 hooks 迁移 | 4.4（余）、4.5 |

Wave 3 的生命体征统一（1.x）涉及历史数据面，上线前需要一次存量盘点脚本 + 去重口径，随任务交付。

---

## 七、需要你拍板的少数几条

1. **随访完成率默认口径**（3.2）：我取"未终态即未完成"的保守默认，并做成可配置 + 标注"待临床确认"；若你要求改成别的，改配置即可，不改代码结构。
2. **`agent_optimized` 是否为预留特性**（4.6）：若是要保留的特性，挂载并补前端入口；若不是，删除。任务 E 会先给证据再按"删除"默认执行。
3. **`device_data` 原始遥测的留存期**（1.1）：收敛后设备原始读数不再存临床事实，保留多久由你定（我默认跟随现有 `retention` 配置，不新造策略）。
