# WP0 领域收敛分析：schema 重复、集合归属与随访链路（2026-11-07）

本文是 BASE03「领域模型收敛」的只读分析记录，不修改任何代码。所有行号基于 2026-11-07 的 main 分支（0da0ab3）工作区快照；路径相对仓库根目录。静态发现不等于运行验收；文中不含真实患者数据。标注「待核实」的结论需在隔离实例上实测后再定。

## 〇、结论速览

1. `backend/app/schemas/health_record.py` 中有 **13 组同名模型重复定义**，Python 模块自上而下执行，后一组（第 371 行起）在运行时整体覆盖前一组；项目实际使用 pydantic 2.4.2（`backend/requirements.txt:6`），与文件内 v1 风格写法（`@validator`、`class Config`、`json_encoders`）混用。
2. `health_record_service.py` 的字段访问**同时混用两代 schema 的字段**：统计方法按第二代写（与生效定义一致），创建/更新方法按第一代写（访问生效模型上不存在的字段），随访与健康档案的创建、更新路径在运行时会抛 `AttributeError`（见 §1.3，待实测核实）。
3. 同一领域对象被指向不同集合：随访 `followup_records` vs `follow_ups`；康复计划 `rehab_plans` vs `rehabilitation_plans`；康复进度 `rehab_progress` vs `progress_records`；患者/医生 `patients`/`doctors` vs `users`。
4. 健康档案路由已注册但存在**路径参数路由遮蔽**（`/{record_id}` 遮蔽 `/followups` 列表）与 `check_permission` 调用签名不匹配两类问题（见 §3.2）。
5. 随访前端链路中，医生端页面为纯模拟数据；健康管理师端走真实 API 但被后端路由遮蔽与 schema 错位双重打断（见 §4）。

---

## 一、重复 schema 清单

### 1.1 同名重复定义（13 组，后定义生效）

生效规则：Python 按模块顺序执行，后面的 class 语句将同名名字重新绑定到新类对象；`health_record_router.py:20-26` 与 `health_record_service.py:9-18` 通过 `from app.schemas.health_record import ...` 拿到的都是**文件中后一次定义**。

| # | 模型名 | 前定义（被覆盖） | 后定义（运行时生效） | 关键字段差异（前 → 后） |
|---|--------|------------------|----------------------|--------------------------|
| 1 | `HealthRecordCreate` | `schemas/health_record.py:151-167` | `schemas/health_record.py:371-375`（继承 `HealthRecordBase:360-368`） | `record_type`: 枚举 `RecordType` → 普通字符串；`content`: `Dict[str,Any]` → **`str`**；`title`: 可选+自动默认 → 必填；`organization_id`、`visibility`、`metadata` 存在于前定义，后定义**没有**，后定义新增 `attachments:List[HealthRecordAttachment]`、`related_items`、`related_follow_ups` |
| 2 | `HealthRecordUpdate` | `schemas/health_record.py:171-177` | `schemas/health_record.py:378-388` | 前定义有 `visibility`；后定义**没有** `visibility`，新增 `record_type`、`related_items`、`related_follow_ups`、`change_description`；`content`: `Dict` → `Optional[str]` |
| 3 | `HealthRecordResponse` | `schemas/health_record.py:181-198` | `schemas/health_record.py:404-414` | 前定义有 `patient_id`、`record_type`、`visibility`、`versions:List[RecordVersion]`、`metadata`；后定义**没有**这些，改用 `content:str`、`current_version:int`、`related_items`、`related_follow_ups`、`updated_by` |
| 4 | `HealthRecordStats` | `schemas/health_record.py:300-310` | `schemas/health_record.py:417-430` | 前定义：`record_types:Dict`、`recent_updates:List[datetime]`、`upcoming_followups:List[Dict]`、`pending_actions`；后定义：`record_type_counts`、`latest_record:HealthRecordResponse`、`upcoming_followups:int`、`recent_activity`、`completion_percentage:float`、`total_attachments` |
| 5 | `HealthTimelineItem` | `schemas/health_record.py:314-328` | `schemas/health_record.py:628-644` | 前定义：`occurred_at`、`created_by`、`related_ids`、自由字符串 `item_type`；后定义：`timestamp`、`data`、`icon`、`color`、`importance`、枚举 `TimelineItemType:617-625`，无 `created_by`/`related_ids` |
| 6 | `FollowUpRecordCreate` | `schemas/health_record.py:202-210` | `schemas/health_record.py:477-482`（继承 `FollowUpBase:465-474`） | 前定义：`created_by` 必填、`notes`、`questions:List[QuestionAnswer]`、`health_record_ids`、`metadata`；后定义：`provider_id`、`description` 必填、`questions:List[FollowUpQuestion]`、`related_records`、`template_id`、`reminder_before`，**没有 `notes`、`health_record_ids`、`metadata`**（`metadata` 在 `FollowUpBase:474`，有） |
| 7 | `FollowUpRecordUpdate` | `schemas/health_record.py:214-224` | `schemas/health_record.py:484-494` | 前定义有 `actual_date`、`notes`、`answers`、`attachments`、`health_record_ids`；后定义**没有**这些，新增 `provider_id`、`description`、`related_records`、`status`、`reminder_before` |
| 8 | `FollowUpRecordResponse` | `schemas/health_record.py:228-246` | `schemas/health_record.py:539-555`（继承 `FollowUpBase`） | 前定义：扁平结构（`questions/answers:QuestionAnswer`、`health_record_ids`、`metadata` 必填）；后定义：新增 `provider_id`、`description`（必填）、`follow_up_result`、`next_follow_up_id`、`template_id`、`completion_data`、`cancellation_data`，无 `health_record_ids`（对应字段改名 `related_records`） |
| 9 | `CompleteFollowUpRequest` | `schemas/health_record.py:250-254` | `schemas/health_record.py:497-503` | `answers`: `List[QuestionAnswer]` 必填 → `List[FollowUpAnswer]` 默认空；`actual_date`: 可选 → 默认 `datetime.now`；后定义新增 `follow_up_result`、`next_follow_up_date`，无 `attachments` |
| 10 | `CancelFollowUpRequest` | `schemas/health_record.py:258-260` | `schemas/health_record.py:506-510` | `reason` → `cancel_reason`；后定义新增 `canceled_by` |
| 11 | `RescheduleFollowUpRequest` | `schemas/health_record.py:264-266` | `schemas/health_record.py:513-517` | `reason`: 可选 → **必填**；后定义新增 `provider_id` |
| 12 | `HealthDataCreate` | `schemas/health_record.py:270-278` | `schemas/health_record.py:569-571`（继承 `HealthDataBase:559-566`） | 数据字段改名：`data:Dict` → **`data_content:Dict`**；前定义有 `device_id`、`metadata`；后定义**没有** `device_id`、`metadata` |
| 13 | `HealthDataResponse` | `schemas/health_record.py:282-296` | `schemas/health_record.py:583-589`（继承 `HealthDataBase`） | 同上改名 `data` → `data_content`；前定义的 `source/device_id/recorded_by` 由基类提供，后定义无独立 `metadata`（基类亦无） |

仅定义一次、无冲突的模型：`RecordType:14`、`FollowUpType:28`、`FollowUpStatus:39`、`RecordVisibility:48`、`Attachment:58`、`VitalSign:68`、`Medication:79`、`LabResult:93`、`Diagnosis:106`、`QuestionAnswer:118`、`MedicalHistory:129`、`RecordVersion:140`、`HealthRecordAttachment:332`、`HealthRecordVersion:343`、`RelatedItem:352`、`HealthRecordBase:360`、`HealthRecordDB:391`、`FollowUpQuestion:434`、`FollowUpAnswer:444`、`FollowUpTemplate:452`、`FollowUpBase:465`、`FollowUpRecordDB:520`、`HealthDataBase:559`、`HealthDataDB:574`、`VitalSignData:592`、`LabResultData:603`、`TimelineItemType:617`。其中 `*DB` 系列只有测试引用（`backend/tests/test_object_id_schema.py:12-17`）。

### 1.2 服务层字段访问与生效 schema 的错位（按生效定义逐项核对）

`health_record_service.py` 对请求数据的字段访问分两代混用：

**按第一代字段访问（生效模型上不存在，预期抛 `AttributeError`，待实测核实）：**

| 位置 | 访问的字段 | 生效模型是否拥有 |
|------|-----------|------------------|
| `services/health_record_service.py:57`（create_health_record） | `record_data.organization_id` | 否（`HealthRecordCreate:371-375` 无此字段） |
| `services/health_record_service.py:60` | `record_data.visibility` | 否 |
| `services/health_record_service.py:130-131`（update_health_record） | `record_data.visibility` | 否（`HealthRecordUpdate:378-388` 无） |
| `services/health_record_service.py:347`（create_followup_record） | `followup_data.notes` | 否（`FollowUpRecordCreate:477-482` 无） |
| `services/health_record_service.py:349` | `followup_data.health_record_ids` | 否 |
| `services/health_record_service.py:411`（update_followup_record） | `followup_data.notes` | 否（`FollowUpRecordUpdate:484-494` 无） |
| `services/health_record_service.py:415` | `followup_data.health_record_ids` | 否 |
| `services/health_record_service.py:794`（create_health_data） | `data.metadata` | 否（`HealthDataCreate:569-571` 无） |

**按第二代字段访问（与生效定义一致，可正常工作）：**

- `health_record_service.py:119` `record_data.change_description`（`HealthRecordUpdate:388` 有）
- `health_record_service.py:273-324`（get_health_record_stats）：构造 `record_type_counts`、`latest_record`、`completion_percentage`、`total_attachments`，与生效的 `HealthRecordStats:417-430` 一致
- `health_record_service.py:481,499,505` `data.follow_up_result` / `data.next_follow_up_date`（生效 `CompleteFollowUpRequest:497-503` 有）
- `health_record_service.py:560,567-568` `data.cancel_reason` / `data.canceled_by`（生效 `CancelFollowUpRequest:506-510` 有）
- `health_record_service.py:789` `data.data_content`（生效 `HealthDataCreate:569-571` 有）

**其他运行时风险点：**

- `services/health_record_service.py:791`：`device_id=data.source == "device"` 把布尔值写进 `device_id` 字段，疑为笔误（应为设备 ID 或不传）。待核实。
- `services/health_record_service.py:491`：`"answers": data.answers` 把 pydantic `FollowUpAnswer` 对象列表直接放入 `$set`，motor/bson 不序列化 pydantic 模型，预期报 `InvalidDocument`（待实测核实）。
- `services/health_record_service.py:1066-1090`（`_map_followup_record_to_response`）：以 `provider_id=created_by`、`description=notes`、`related_records=health_record_ids` 等映射把第一代存储结构适配到第二代响应，属于两代契约的"缝合层"；`reminder_settings` 用 `hasattr` 兜底（`health_record_service.py:1086`）。

### 1.3 与数据库模型（models）的关系

- 文档模型（带 `collection_name` 的普通类）在 `backend/app/models/health_record.py`：`HealthRecord:11-13`（集合 `health_records`）、`FollowUpRecord:123-125`（`followup_records`）、`HealthData:232-234`（`health_data`）、`MedicalTimeline:347-349`（`medical_timelines`）。服务直接实例化这些类并 `to_mongo()` 写库（如 `health_record_service.py:63-67、353-355`），**pydantic schema 仅作请求/响应契约，未参与存储校验**。
- 因此 schema 覆盖问题主要影响 API 请求解析与响应构造；库内文档结构由 `models/health_record.py` 决定。收敛时不能只改 schema，须同时核对已入库文档的真实字段。

---

## 二、集合名对应表

按 `grep -rnE "\bdb\[|\bdb\.[a-z_]+" backend/app --include="*.py"` 全量盘点（排除 `db.client/ping/command` 等非集合访问）。

### 2.1 同一领域对象指向不同集合（收敛重点）

| 领域对象 | 集合名 A | 引用位置 | 集合名 B | 引用位置 | 说明 |
|----------|----------|----------|----------|----------|------|
| 随访记录 | `followup_records` | `models/health_record.py:125`；`services/health_record_service.py:33`（读写全走此集合） | `follow_ups` | `api/routers/doctor_router.py:180`（医生端读）；`mock_data_scripts/create_test_health_records.py:266,370`（造数脚本写，字段为 `title/content/doctor_id/doctor_name/completed_date`，与服务端 `patient_id/created_by/health_record_ids/actual_date` 结构不同） | 医生端读的集合服务端从不写；查询字段也不同（`doctor_id` vs `created_by`，`doctor_router.py:174`） |
| 康复计划 | `rehab_plans` | `services/rehabilitation_service.py:20`；`services/prediction_service.py:19`；`services/agent_service.py:654,677` | `rehabilitation_plans` | `models/rehabilitation.py:79`（模型声明）；`mock_data_scripts/create_test_rehab_plans.py:202-203,271`（造数写此集合） | 模型声明的 `collection_name` 无任何代码使用；服务与造数各写一个集合 |
| 康复进度 | `rehab_progress` | `services/prediction_service.py:20` | `progress_records` | `models/rehabilitation.py:195`（`ProgressRecord.collection_name`） | 同上，模型声明无引用 |
| 康复评估 | `rehab_assessments` | `services/rehabilitation_service.py:22`；`services/prediction_service.py:18`；`services/multimodal_service.py:14` | 无模型定义 | `backend/app/models/` 下未找到评估模型的 `collection_name` | 待核实：是否存在独立的评估集合契约 |
| 患者/医生 | `users` | `models/user.py:14`（`User.collection_name`，`Doctor/Patient` 继承）；`services/user_service.py:27`；`api/routers/doctor_router.py:89,97,110`；`core/dependencies.py:245` | `patients`、`doctors` | `services/analytics_service.py:17-18`；`services/report_scheduler_service.py:282` | 分析与报表服务读取的集合没有对应的常规写入路径（待核实是否有历史数据或外部写入） |
| 用药/体征明细 | `health_data` | `services/health_record_service.py:35`；`models/health_record.py:234` | `exercise_logs` | `services/multimodal_service.py:15` | 多模态服务自建日志集合，无模型契约 |

### 2.2 引用一致的集合（现状无冲突，收敛时一并冻结命名）

| 集合名 | 主要读写方（file:line） |
|--------|--------------------------|
| `health_records` | `services/health_record_service.py:31`；`services/multimodal_service.py:16`；`core/dependencies.py:249` |
| `health_data` | `services/health_record_service.py:35` |
| `medical_timelines` | `services/health_record_service.py:37` |
| `users` | `services/user_service.py:27`；`db/crud.py:25`（经 `model_class.collection_name`） |
| `devices` / `device_data` / `device_repair_logs` | `services/device_service.py:23,100,360`；`services/device_repair_service.py:35,66`；`services/device_adapters.py:60`；`models/device.py:11,103,160` |
| `health_data_thresholds` / `health_data_alerts` | `services/health_alert_service.py:32,34`；`models/health_data_threshold.py:11,351` |
| `messages` / `conversations` | `services/communication_service.py`；`models/communication.py:12,85` |
| `notifications` | `services/notification_service.py:37-225` |
| `agents` / `agent_interactions` / `agent_cache` | `services/agent_service.py:25,151`；`models/agent.py:36,124` |
| `llm_generations` | `services/agent_service.py:226,261,702` |
| `report_schedules` / `reports` | `services/report_scheduler_service.py:70-631` |
| `saved_filters` | `services/data_filter_service.py:359-405` |
| `exercises` | `services/rehabilitation_service.py:21`；`models/rehabilitation.py:12`（唯一一致的对齐案例） |
| `audit_logs` | `services/audit_log_service.py` |
| `integration_fill_tasks` | `integrations/forms/models.py:27`；`integrations/forms/service.py:158-266`（唯一用常量 `COLLECTION_NAME` 收敛的模块，可作范本） |
| `patientmanager.daily_records` | `api/routers/patient_router.py:28,88-192` | 带库名前缀的跨库命名，与其余集合命名风格不一致，待核实是否确属另一数据库 |
| `health_metrics` / `todo_items` | `services/dashboard_service.py:35,48`；仅 `mock_data_scripts/init_dashboard_data.py:64,133,153` 写入 | 纯演示数据链路，对应 `models/health_record.py:472,497` 的 `HealthMetric/TodoItem`（无 `collection_name`） |

---

## 三、路由注册现状

### 3.1 注册清单（`backend/app/main.py`）

| Router | 注册位置与最终前缀 | 内部前缀 | 权限控制方式 |
|--------|--------------------|----------|--------------|
| `user_router` | `main.py:193` → `/api/users` | 无 | 依赖注入（`core/auth.py`） |
| `rehabilitation_router` | `main.py:194` → `/api/rehabilitation` | 无 | 待核实（`rehabilitation_router.py` 未逐条核查） |
| `agent_router` | `main.py:195` → `/api/agents` | 无 | 待核实 |
| `doctor_router` | `main.py:198` → `/api/doctors` | 无 | 每个处理函数内手写 `current_user.role != "doctor"` 判断（如 `doctor_router.py:21-22`） |
| `health_manager_router` | `main.py:199` → `/api/health-managers` | 无 | 同上（`health_manager_router.py:14-15` 等） |
| `patient_router` | `main.py:200` → `/api/patients` | 无 | `get_current_user` + 手写角色判断（`patient_router.py:103-104`） |
| `system_admin_router` | `main.py:201` → `/api/admin` | 无 | 待核实 |
| `health_record_router` | `main.py:203` → `/api` + 内部 `/health-records`（`health_record_router.py:29`） | `/health-records` | `Depends(is_medical_staff)` 工厂 + 函数体内调用 `check_permission`（存在问题，见 §3.2） |
| `health_alert_router` | `main.py:205` → **无外部前缀**，内部自带 `/api/health/alerts`（`health_alert_router.py:17-18`） | `/api/health/alerts` | 待核实。最终路径仍是 `/api/health/alerts`，但前缀写法与其他路由相反（外部不传 prefix、内部写死完整路径），易在调整时双前缀 |
| `notification_router` | `main.py:207` → `/api/notifications` | `/notifications` | 待核实 |
| `communication_router` | `main.py:210` → `/api/communications` | `/communications` | 待核实 |
| `report_scheduler_router` | `main.py:213` → `/api/report-schedules` | `/report-schedules` | 待核实 |
| `data_filter_router` | `main.py:214` → `/api/data-filters` | `/data-filters` | 待核实 |
| `device_router` | `main.py:217` → `/api/devices` | `/devices` | 待核实 |
| `device_repair_router` | `main.py:218` → `/api/device-repairs` | `/device-repairs` | 待核实 |
| `device_data_standard_router` | `main.py:219` → `/api/device-standards` | `/device-standards` | 待核实 |
| `audit_log_router` | `main.py:223` → `/api/audit-logs` | `/audit-logs` | 待核实 |
| `analytics_router` | `main.py:227` → `/api/...`（内部无前缀，`analytics_router.py:9`） | 无 | 待核实 |
| `integration_forms_router` | `main.py:231` → `/api/...`（`integrations/forms/router.py`） | 待核实 | 待核实 |

**定义了但未注册：**

- `device_analysis_router`（`api/routers/device_analysis_router.py:14`，内部前缀 `/device-analysis`）：在包 `__init__` 中导入（`api/routers/__init__.py:12`），但 `main.py` 无对应 `include_router`，整组接口不可达。
- `auth_router`：在 `api/routers/__init__.py:17` 被注释，"暂未实现"。

### 3.2 `health_record_router` 的两个结构性问题

1. **路径参数路由遮蔽**（FastAPI 按注册顺序匹配）：
   - `GET /{record_id}`（`health_record_router.py:57`）注册在 `GET /followups`（`health_record_router.py:365`）之前 → `GET /api/health-records/followups?patient_id=...` 会命中 `get_health_record`，把 `"followups"` 当作 record_id 查询，返回 404。前端 `api.ts:287-288` 的列表调用正走此路径。
   - `GET /followups/{followup_id}`（`health_record_router.py:246`）注册在 `GET /followups/upcoming`（`health_record_router.py:403`）之前 → `upcoming` 会被当作随访 ID。
   - 健康档案自身的 `GET /stats/{patient_id}`（`:199`）、`GET /version/{record_id}/{version_number}`（`:169`）为两段路径，与一段的 `/{record_id}` 不冲突，但与 `/followups/*` 一样都排在 `/{record_id}` 之后——新增子资源路由若只有一段同样会被遮蔽。
2. **`check_permission` 调用签名不匹配**：`core/dependencies.py:134` 定义 `def check_permission(permission: str)` 返回依赖工厂；而 `health_record_router.py:77、154、189、212` 在函数体内写成 `await check_permission(current_user, Permission.VIEW_ANY_HEALTH_RECORD)`——多传一个位置参数且把工厂当普通函数调用，运行到该分支会抛 `TypeError`（待实测核实）。`health_record_router.py:119` 的 `Depends(check_permission(Permission.HEALTH_RECORD_DELETE))` 用法是正确的，两种写法并存。

### 3.3 角色路由中的假 ID / 空响应 / 模拟数据（后端）

- `doctor_router.py:34-48、53-67`：患者列表查不到或出错时返回 5 条硬编码模拟患者（`id: mock_1..5`）。
- `doctor_router.py:198-207`：`POST /follow-ups` 不写库，返回 `{"id": "new_follow_up_id"}`。
- `doctor_router.py:210-221、224-233、235-244、247-256、259-268、270-279`：监测、沟通、统计、知情同意等端点全部返回 `{}`/`[]`/假 ID，且沟通假 ID 与真实的 `messages/conversations` 集合服务（`communication_service.py`）并存。
- `health_manager_router.py:11-101`：整个路由为占位实现（返回 `[]`/`{}`/`"new_follow_up_id"`/`"new_message_id"`），无任何服务层调用。

---

## 四、随访链路：真实 / 占位对照

### 4.1 后端读写路径

| 路径 | 集合 | 字段契约 | 真实性 |
|------|------|----------|--------|
| `/api/health-records/followups`（POST/GET/PUT、complete/cancel/reschedule/upcoming，`health_record_router.py:222-457`）→ `HealthRecordService`（`health_record_service.py:331-770`） | `followup_records` | 第一代存储结构（`models/health_record.py:123-229`） | 设计为真实链路，但受 §1.2 字段错位与 §3.2 路由遮蔽影响，创建/更新/列表预期不可用（待实测核实） |
| `/api/doctors/follow-ups` GET（`doctor_router.py:161-196`） | `follow_ups`，按 `doctor_id` 过滤 | 造数脚本结构（`mock_data_scripts/create_test_health_records.py:353-364`） | 读真实集合，但该集合只有造数脚本写入；与服务端 `created_by` 字段不匹配 |
| `/api/doctors/follow-ups` POST（`doctor_router.py:198-207`） | — | — | 占位，返回假 ID |
| `/api/health-managers/follow-ups` GET/POST（`health_manager_router.py:32-52`） | — | — | 占位，空列表/假 ID |
| 时间线联动 | `medical_timelines` | `models/health_record.py:411-432` | 真实，与服务端随访写路径绑定 |
| 造数脚本 | `follow_ups` | 同医生端 | 演示数据，字段结构与服务端写入的 `followup_records` 不同 |

### 4.2 前端调用

| 页面/组件 | 调用 | 后端落点 | 真实性 |
|-----------|------|----------|--------|
| 医生端 `pages/Doctor/FollowUpManagement.tsx`（路由 `frontend/src/routes.tsx:300,323`） | **不调用任何 API**：`mockFollowUps`（`FollowUpManagement.tsx:15-84`）、模拟延迟（`:117-124`）、模拟完成/取消（`:182-236`） | — | **纯模拟** |
| 医生端 `api.ts:222-226` `doctor.getFollowUps/createFollowUp` | `/doctors/follow-ups` | `doctor_router.py:161-207` | 读真实（但集合与字段错位），写为占位。代码库内未见页面调用此组方法（待核实是否有动态调用） |
| 健康管理师端 `pages/HealthManager/HealthRecords.tsx:139-166,246-249` | `apiService.getFollowUps/createFollowUp/updateFollowUp`（`api.ts:287-294`） | `/health-records/followups` | **真实调用**，但被 §3.2 路由遮蔽（GET 列表）与 §1.2 schema 错位（POST/PUT）双重打断 |
| `components/HealthManager/FollowUpForm.tsx`、`FollowUpReminderComponent.tsx`、`FollowUpList.tsx` | 纯展示/表单组件，无直接 API | — | 由父页面注入数据 |
| `services/notificationService.ts:8,29` | 仅类型/偏好字段提及 `followup` | — | 不构成读写链路 |

### 4.3 康复方案的"模拟计划"问题（与随访同属 BASE03 范围）

- `services/agent_service.py:464-553`：LLM 调用失败时回退到 `mock_response` 模拟康复计划并以正常返回值对外，调用方无法区分真实生成与模拟（对应 baseline 第 20 行结论）。
- `services/agent_service.py:654,677` 对生成计划的审核写 `rehab_plans` 集合，与模型声明的 `rehabilitation_plans`（`models/rehabilitation.py:79`）及造数脚本（`create_test_rehab_plans.py:271`）分裂。
- `services/agent_service.py:683`：`plan["metadata"]["approval_history"].append(...)` 在 `approval_history` 不存在时会 `KeyError`（待实测核实）。

---

## 五、收敛建议与迁移注意点

### 5.1 每个领域对象的唯一契约建议

| 领域对象 | 建议唯一 schema（pydantic v2 风格） | 建议唯一集合名 | 建议唯一服务入口 |
|----------|--------------------------------------|----------------|------------------|
| 健康档案 | 保留第二代骨架（`HealthRecordBase/HealthRecordDB/HealthRecordResponse`，`schemas/health_record.py:360-414`），补回前定义中的 `visibility`、`organization_id`、`metadata`、枚举 `RecordType`；`content` 需决策：前代 `Dict`（结构化）vs 后代 `str`——建议 `Dict`，与 `models/health_record.py:21` 及版本机制（`models/health_record.py:85-103`）一致 | `health_records`（现状已是唯一写入名，保持） | `HealthRecordService` 唯一入口；`core/dependencies.py:239-289` 的 `get_health_record_for_patient`（自己拼档案结构）与 `doctor_router.py:70-158` 的映射层应改为调用同一服务方法 |
| 随访 | 二选一并全量对齐：建议以第二代（`FollowUpBase/FollowUpRecordDB/FollowUpRecordResponse:465-555`）为骨架（字段更完整、含模板与提醒），同时把第一代独有的 `health_record_ids`（关联档案）、`answers:QuestionAnswer` 结构并入；`FollowUpStatus` 枚举统一 `canceled` 拼写（models 用 `cancelled`，`models/health_record.py:206`，schema 用 `canceled`，`schemas/health_record.py:42`） | 建议 `follow_ups` 或 `followup_records` **二选一**；选定时另一集合只读迁移后废弃 | `HealthRecordService` 的随访方法组；`doctor_router.py:161-207`、`health_manager_router.py:32-52` 全部改为转调服务，不得直连 `db["follow_ups"]` |
| 康复计划 | `models/rehabilitation.py:77-140` 为唯一文档模型，补齐对应 schema（当前无 plan 的 pydantic 契约，路由直传 dict） | 需决策：`rehab_plans`（三个服务在写）vs `rehabilitation_plans`（模型声明+造数脚本）；建议以**实际库中有数据的一侧**为准（待核实：隔离实例上 `list_collection_names` 比对两集合文档数） | `RehabilitationService`；`agent_service.py:654-687` 的审核逻辑应迁入或经其调用 |
| 康复评估 | 当前无模型，先建契约再收敛（`rehab_assessments` 三处引用一致，可作为暂定名） | `rehab_assessments` | 同上 |
| 康复进度 | `ProgressRecord`（`models/rehabilitation.py:193-195`）vs `rehab_progress`（`prediction_service.py:20`）需合并为一份契约 | 同上二选一 | 建议进 `RehabilitationService` 或独立 `ProgressService`，prediction 只读 |
| 健康数据 | 第二代（`HealthDataBase/HealthDataDB/HealthDataResponse:559-589`），把 `device_id`、`metadata` 补进 `HealthDataBase` | `health_data` | `HealthRecordService` 健康数据方法组 |
| 时间线 | `HealthTimelineItem` + `TimelineItemType`（`schemas/health_record.py:617-644`），废弃第一代（`:314-328`） | `medical_timelines` | 随写路径内联生成（现状），可抽为 `MedicalTimelineService` |
| 演示数据 | `HealthMetric/TodoItem`（`models/health_record.py:472-519`）无 `collection_name`，仅 dashboard 与造数使用 | `health_metrics`/`todo_items` | 建议明确标记为 demo-only 并从主服务剥离，或纳入正式模型 |

### 5.2 迁移与兼容注意点

1. **先盘点真实库再动代码**：在隔离实例上对上述每个分歧集合执行 `list_collection_names` + 文档抽样，确认哪一侧有真实数据。本文全部为静态结论，不能作为迁移依据（呼应 baseline 第 23 行）。
2. **不得直接删除或覆盖集合**：`follow_ups` 与 `followup_records` 字段结构完全不同（`doctor_id/doctor_name/completed_date` vs `created_by/health_record_ids/actual_date`），合并需要字段级映射脚本，而不是改名了事；`rehab_plans` 与 `rehabilitation_plans` 同理。
3. **schema 收敛顺序**：先删同名覆盖（保留决策后的那一版），再修 `health_record_service.py` 的字段访问（§1.2 表中的 8 处），否则修复 schema 后服务端仍会 `AttributeError`。建议为创建/更新/列表/完成/取消/改期各写一条隔离实例集成用例后再切流量。
4. **路由顺序修复**：把 `health_record_router.py` 的 `GET /followups`、`GET /followups/upcoming`、`GET /stats/{patient_id}`、`GET /version/...` 全部移到 `GET /{record_id}`、`PUT /{record_id}`、`DELETE /{record_id}` 之前（或把 `/{record_id}` 收窄为 `/{record_id:path}` 之外的模式）；同时统一 `check_permission` 用法：函数体内一律改用 `Depends` 工厂（§3.2）。
5. **造数脚本与契约同步**：`create_test_health_records.py`、`create_test_rehab_plans.py`、`init_dashboard_data.py` 写入的集合与字段必须随唯一契约同步更新，否则收敛后演示环境会继续制造第二套数据。
6. **pydantic v2 迁移一并完成**：`schemas/health_record.py` 全文使用 v1 风格 `@validator`（`:163`）、`class Config` + `json_encoders`（`:307-310、427-430、641-644`），在 pydantic 2.4.2 下为弃用行为；收敛时应改为 `field_validator`/`model_config`，并保留 `tests/test_object_id_schema.py` 的 ObjectId 严格契约测试作为回归门。
7. **模拟数据出口要有显式状态**：`agent_service.py:464-553` 的模拟计划回退应改为显式失败状态（HTTP 错误或 `generation_status=failed`），`doctor_router.py:34-67` 的模拟患者列表同理；收敛后任何假 ID（`new_follow_up_id`、`mock_*`）都不应出现在正式响应中。
8. **权限边界同步收敛**：随访与健康档案当前存在三套写法（函数内手写角色、`is_medical_staff` 依赖、`check_permission` 工厂）+ 对象级归属校验不一致（`doctor_router.py:87-103` 自查 `users` 集合）。统一 repository 时应一并明确"服务层做对象归属校验、路由层做角色/权限声明"的分层，避免 `include_router` 即视为权限正确（呼应 baseline 第 19 行）。
9. **`patientmanager.daily_records` 与 `health_alert_router` 的前缀异常**：前者是跨库命名（`patient_router.py:28`），后者是内部写死完整路径（`health_alert_router.py:17-18`）；收敛命名时确认是否保留，避免迁移时误判为同库集合。

### 5.3 本轮未覆盖（下一步）

- 康复反馈前后端路径/方法不一致的具体断点（baseline 第 20 行）未逐条核对，待康复链路专项。
- `analytics_service.py:17-20`、`report_scheduler_service.py:282,330` 读取的 `patients/doctors/rehabilitation_records/rehabilitation_sessions` 集合的数据来源未定位（待核实）。
- 全部结论需在隔离 MongoDB 实例上以只读集合清单与最小集成用例复核后，才能作为收敛实施依据。
