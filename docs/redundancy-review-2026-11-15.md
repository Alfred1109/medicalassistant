# 冗余审查报告与收敛路线（2026-11-15）

审查方式：5 个只读审查代理分层覆盖（R1 服务层横向、R2 API/模式层、R3 前端、R4 数据架构、R5 分层与依赖方向），全部结论经 grep/AST 零引用验证或逐 file:line 核实。审查基准：当日工作区（患者档案波次 1–6 + 功能批次已提交）。

## 总览

| 维度 | 主要发现 |
|---|---|
| 死代码 | 前端约 25 个孤儿组件 + 4 个孤儿页面 ≈ **5500 行**；后端 core/utils.py 整文件、若干 0 引用模型与函数；api/endpoints/ 三个未挂载死路由 |
| 代码冗余 | 后端：事务样板五件套 ×4 服务、UTC 时间戳归一 5 种命名、错误壳 ×4、$facet 分页 ×3、域分派样板重复实现内核能力；前端：错误提取 10 套、日期格式化 20+ 份、ICF 类型双份、4 条请求通道并存 |
| 架构冗余 | review 状态机三份注释复制；三套人工关联设施同构未收敛；配置集合 6+ 种模式；doctor/HM router 整文件复制；API 重叠矩阵（患者列表/健康档案/随访列表各 3 入口）；依赖方向违规 8 项（core→services、services⇄websockets 真循环等） |
| 逻辑冗余 | patient_domain_mode 单请求多次读取；三层重复归属/可用性校验（形态不一）；分页约束三层重复 |

---

## 批次 1：零/低风险快赢（可直接执行）

### 死代码删除
- **前端**（约 -5500 行，删除前 tsc --noEmit 兜底防 barrel 泄漏）：healthDataService.ts；RehabAssessmentReport/ 目录（8 文件，连带孤儿 dateUtils.ts）；components/Analytics 4 个孤儿（保留 AnalyticsChart）；components/Dashboard 3 个；components/HealthManager 8 个孤儿；TrainingTimer、ElectronicSignature、ConsentDocumentTemplates×2、RehabPlanDisplayComponent；孤儿页面 RehabPlanPage/AgentManagementPage/HealthDataManagement/ConsentNotice；routes.tsx 的 test/feature-demo 测试路由下线。
- **后端**：core/utils.py 整文件；core/cache.py 的 invalidate_cache/cached；core/config.py 的 4 个零引用函数；core/dependencies.py 的 check_any_permission/check_all_permissions/is_admin；core/permission_audit.py 的 tracker 两个函数；audit_log_service.log_role_assignment；device_data_validator_service 的 validate_complex/normalize；device_repair_service 的 create/get_stats；device_service 的 3 个零引用方法；icf_service._report_item_rows；0 引用模型（RehabProgress/AgentTool/AuditLog/HealthMetric/TodoItem/DeviceCollectionSession）；crud_services 的无消费 CRUD 方法。
- **待决策孤儿**：agent_optimized_service + api/endpoints/ 三文件（挂载或删除——需确认是否预留特性）；report_scheduler 执行链（已登记的有意孤儿，收敛需先完成扫描重写）。

### 模式收敛（纯提取，低风险）
- 后端：事务样板五件套 → `run_transaction_with_dedup_retry`；UTC 归一 5 种命名 → 单一助手；$facet 分页 ×3 → `paged_aggregate`；`is_domain_state_unavailable` 分流五连 → `reraise_or_domain_error`；`patient_domain_mode_safe`（fail-safe unknown 口径合一，替代 analytics/data_export/quality_process 三处包装）；角色→归属字段裸三元 4 处改调 `patient_assignment_field`（行为收紧：未知角色从静默兜底变抛错，逐点确认输入域）；审计脚本公共脚手架 `scripts/_audit_common.py`。
- 前端：三份 getApiErrorMessage → patientErrors 家族工厂；User/Patient/Device/ICF 类型去重到 types/；PatientMainDashboard 通知改走 notificationService；config/apiPaths 统一路径引用；api.ts 设备组并入 deviceService（去死参数）。

### 索引与安全收尾
- health_alert_service 死索引声明（initialize 零调用方）删除，alerts 补 `(patient_id, recorded_at)` 复合索引纳入 db/indexes.py；clinical_patient_name_query 双声明点收敛单属主；fences.create_account_fence_indexes 补迁移脚本接线。

## 批次 2：中风险分波段（结构收敛，需逐域验证）

1. **域分派撤回内核**（R1-A1，最大一块）：服务层 5 处重复实现的 canonical/legacy 患者读取撤到内核 `load_patient_doc`/`resolve_self_patient_entity`，服务层只保留业务错误码映射。首选样板：rehab_publication `_authorize_canonical` 整体删除。风险：错误码族绑定与事务内嵌，分波段。
2. **legacy 栅栏块提取**（R1-A2）：7 处复制粘贴 → `fences.legacy_document_fence`；rehab_feedback 与 publication 对同一计数器的两套实现合一。注意 followup_service 多一个 `deleted` 条件，核对语义后统一。
3. **账号身份读取统一**（R1-A3）：`resolve_unique_account` 收敛四套 `_account`；核对 raw 读取与 load_identity_groups 的歧义行为差异。
4. **review 状态机收敛**（R4-A1）：三份注释复制的实现 → `review_state_machine.py`（快照构造留回调）；clinical 的 legacy_review 兼容分支保留为专属钩子。
5. **三设施公共基座**（R4-1.3）：`core/reviewed_link.py` 只收敛四件真同构事（review 校验、insert+冲突映射、disable 三态判定、审计条目 schema 适配层）；各设施保留源引用校验/反向复核/错误码；**历史文档不动**。
6. **前端架构收敛**（R3）：菜单/路由单源配置化（先补路由-菜单一致性快照测试）；api.ts 康复域合并；DataMonitoring 双页合并评估；共享 useAsyncResource + PatientSelect 分批迁移。
7. **API 重叠收敛**（R2）：doctor/HM router 合并为 provider 工作台（依赖工厂注入角色，删空壳存根端点——先确认前端未调）；followups 三入口收敛单正典；alerts 读取统一走 service（clinical 侧裸投影改造）。

## 批次 3：依赖方向修复（R5，配合批次 2）

- V1：core/dependencies.py（服务容器）迁移至 api/ 或 services/container.py——core 恢复纯底座。
- V4：services⇄websockets 真循环（6 处延迟 import）→ PushNotifier 协议注入或 ws_manager 移中性模块。
- V5：followup⇄forms 循环 → followup 并发语义常量下沉中性模块。
- V2/V3：auth⇄user_service、permissions→AuditLogService → 权限常量下沉 / AuditSink 协议。
- main.py 收敛：路由注册列表化、startup 编排抽 bootstrap.py、maintenance_gate 角色解析改走 core.auth。

## 批次 4：需设计决策（不动手，先拍板）

1. **ConfigStore 统一**：6+ 配置模式收敛为参数化 ConfigStore（fail 语义刻意分化必须保留为参数）；icf 读时播种违反启动期不隐式建集合的约定，外迁到维护脚本/首写路径。
2. **legacy is_active 精化上提**（R1-L2）：会改变 legacy 停用患者可见性契约，涉及与 C1 业务决策（停用患者可见性口径）联动。
3. **双域分支清理登记**：给每个 legacy 分支打两类标签——①域分派分支（迁移完可删）②legacy 数据形态兼容（legacy_user_id/submission_history 等，**永不删除**）——R5 指出目前无标注是清理最大执行风险。
4. **device_data 幂等唯一索引**：先跑盘点（沿 label_uniqueness_audit 流程）再建。
5. **alerts→notifications 桥接**（可选，非冗余问题）。

## 明确非冗余（审查确认保留）

- 双审计体系（audit_logs 访问审计 vs 链接内嵌业务审计）——后者是承重的授权证据。
- access 家族在 core/ 的位置（本仓做得最好的部分）；icf_service 的延迟 import 是合理服务集合门面（非循环）。
- operations/directory/integrations 独立层（登记进分层文档即可）。

---

**执行建议**：批次 1 立即执行（一次提交或分 2-3 个主题提交）；批次 2 按 1→2→3→6→4→5→7 顺序分波段；批次 3 与批次 2 的对应波段合并做；批次 4 的决策点集中一次给你拍板。
