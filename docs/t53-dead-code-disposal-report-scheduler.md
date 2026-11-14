# T53 决策记录：report_scheduler 死代码处置（删除调度路径）

日期：2026-11-15 · 结论：选项 a（删除死代码）

## 对象

`backend/app/services/report_scheduler_service.py` 的 `start()`、`stop()`、
`_scheduler_loop()`（及其派生实例状态 `is_running` / `_scheduler_task`）。

## 兼容分析

1. **引入原因（git 溯源）**：`start()` 自仓库起源提交 `dac0330`
   （2025-05-10，"update"）即存在，属初始随附代码，从未被接入应用生命周期。
2. **调用链核查**：全仓 `start` 无调用方。`main.py` 不启动本服务；
   `report_scheduler_router.get_report_scheduler_service` 按请求实例化
   `ReportSchedulerService(db=...)` 仅做 CRUD（创建/更新/删除/查询/启停开关），
   不触发调度；无任何部署脚本、运维文档引用 `start`。`stop()` 同样无调用方
   （`main.py` 的 `backup_schedule.stop` 是 operations/runtime 的另一对象）。
3. **已知缺陷**：`_scheduler_loop` 为 fire-then-update——`create_task` 执行
   `_process_schedule` 后立即 `_update_next_run_time`，无原子领取。T34 已确认
   若启用即复刻 D1 缺陷（多 worker 重复执行同一调度任务）。T37 已为备份调度
   （operations/runtime.py `run_if_due`）落地 `find_one_and_update` 原子领取的
   正确范式。
4. **_process_schedule 执行链的独立价值评估**：
   `_process_schedule → _generate_report → _export_report / _send_report_email`
   与 `_update_next_run_time` 仅可经 `_scheduler_loop` 到达，调度路径删除后
   同为不可达；但该执行链被领域收敛文档引用（orphan-read TODO 登记于
   `_get_rehabilitation_stats`、患者集合名常量 `PATIENTS_COLLECTION_NAME`
   见 `docs/patient-domain-cutover-plan.md`），且承载待业务决策的报表生成/
   邮件发送复用件。**保留执行链**，并在模块头与 `_process_schedule` 入口
   固化警示：恢复调度前必须先按 T37 同款原子领取重写扫描逻辑。

## 处置

- 删除 `start()`、`stop()`、`_scheduler_loop()`、`is_running`、
  `_scheduler_task`；顺带清理因此不再使用的 `asyncio` 导入，以及自引入即
  未使用的 `device_analysis_service`、`typing.Union` 导入。
- 保留：路由 CRUD 全部方法（按请求实例化）、执行链方法、错误码、
  `PATIENTS_COLLECTION_NAME`、孤儿集合读取 TODO。
- 模块头注释登记删除依据与恢复前置条件（原子领取）。

## 影响面

- `tests/test_report_scheduler_dependency.py`：改以「单例 `db` 保持 None」
  断言全局调度器未被 CRUD 触碰（原 `is_running` / `_scheduler_task` 状态
  断言随删除移除；全局 `get_db` 打桩 AssertionError 防线不变）。
- `tests/test_orphan_collection_reads.py`、
  `tests/test_background_scheduling_replica.py`：仅注释同步（不再指向已
  删除的 `start()`）。

## 恢复条件（未来若需要后台报表调度）

1. 先按 T37 范式实现原子领取（filter 含到点条件，领取成功者才执行）；
2. 再新增显式启动入口并接入应用生命周期 + shutdown 停止；
3. 补多进程并发验证用例（参照 `test_background_scheduling_replica.py`）。
