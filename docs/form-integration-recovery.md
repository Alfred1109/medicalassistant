# 填报任务事务失败与远端会话核查

本说明覆盖独立填报任务及关联随访节点的填报任务。创建任务的本地持久化统一使用副本集事务，关联节点时反向索引也在同一事务；确认时任务与节点状态同事务提交。远端 HTTP 调用在事务外执行。部署前提见 [MongoDB 部署说明](../deploy/mongodb/README.md)。

所有新任务均在创建远端会话前检查 MongoDB 的副本集/分片和逻辑会话能力，standalone 返回 `FOLLOWUP_TRANSACTION_UNAVAILABLE`，不会先创建远端会话。此检查仅是部署前置检查，不能保证后续事务成功；检查后发生的写入、网络或提交故障仍按以下恢复流程处理。早期使用 standalone 的隔离嵌入试点需要改用副本集后才能创建新任务，既有任务的读取与展示不因此改写。

医护任务详情、嵌入链接、确认和取消均要求当前仍是任务发起人且仍在患者本地 `practitioners` 归属中；列表在分页和计数前限定当前归属患者。患者角色不能复用旧医护身份访问该医护任务，admin 沿用既有本地豁免。这只是本地归属校验，不能代替 113.44 统一主体、中心权限、撤权时限及进行中请求的源授权控制（AUTH04）。

当前没有自动扫描、自动重试或自动清理恢复事件的后台任务。`integration_recovery_events` 是待人工核查记录，不是正在运行的队列消费者。禁止对提交结果未知的创建请求直接重新创建任务：远端会话和原本地事务可能已经成功。

## 创建失败的行为

- 本地事务确认失败且可以确认没有已提交任务时，服务尝试通过已有的远端 `POST /integration/v1/fill-sessions/{session_uuid}/cancel` 撤销会话，再记录 `integration_fill_tasks.status=failed`。
- 撤销失败时，失败任务记录 `cleanup_required=true`，响应为 `FILL_TASK_CLEANUP_REQUIRED`。这不是成功绑定，也不会给原节点追加任务引用。
- `commit_result_unknown=true` 时不撤销远端会话，不把任务标成失败；服务在 `integration_recovery_events` 记录 `status=pending_commit_verification`、`task_id`、`session_uuid`、`followup_visit_id`、操作者和时间，返回 `FILL_TASK_COMMIT_UNCERTAIN`。
- 恢复审计本身写入失败时，响应为 `FILL_TASK_RECOVERY_UNCERTAIN`，包含核查所需的任务和会话标识。此时数据库中可能没有恢复记录，需保留调用端收到的错误。服务不在日志或恢复事件中保存明文嵌入令牌。

## 只读核查

使用目标环境受控的数据库维护账号。先核实环境、数据库名以及错误响应中的精确标识，不按患者姓名、时间接近或其他会话代替匹配。

1. 在 `integration_recovery_events` 中按恢复记录 `_id` 查询；若审计失败，则直接使用错误响应的 `task_id` 和 `session_uuid`。
2. 按 `ObjectId(task_id)` 查询 `integration_fill_tasks`；比较 `followup_visit_id` 及 `session.session_uuid`（旧记录也可能保存在 `fill_sessions`）。不要输出整个文档，尤其不要输出嵌入 URL、令牌哈希或远端答案。
3. 按关联节点 `_id` 查询 `followup_records` 的 `status`、`fill_task_ids`、`mutation_version`。创建事务成功应同时存在任务及其反向引用。确认事务成功应同时存在任务 `confirmed` 与节点的同任务 `effective_response`；后续取消等合法操作可能已改变节点状态，应结合时间和操作记录核查，不能直接回写旧状态。
4. 使用已有表单平台客户端 `get_fill_session(session_uuid)` 查询远端，只记录会话状态和答卷引用。不要重新创建会话来“验证”。
5. 若本地任务缺失，先恢复数据库稳定性并确认原事务最终结果；一次立即读取未见任务不足以证明未知提交已失败。若仍无法确认，保留待核查状态，不撤销、不重新创建。

示例只读投影（在已选定数据库的 Mongo shell 中执行，用精确 ID 替换占位值）：

```javascript
db.integration_recovery_events.findOne(
  {_id: ObjectId("RECOVERY_ID")},
  {task_id: 1, session_uuid: 1, followup_visit_id: 1, status: 1, created_at: 1}
)
db.integration_fill_tasks.findOne(
  {_id: ObjectId("TASK_ID")},
  {status: 1, followup_visit_id: 1, "session.session_uuid": 1,
   "session.response_id": 1, cleanup_required: 1, updated_at: 1}
)
db.followup_records.findOne(
  {_id: ObjectId("VISIT_ID")},
  {status: 1, fill_task_ids: 1, "effective_response.task_id": 1, mutation_version: 1}
)
```

## 人工处置与留证

确认已提交且引用一致时，保留任务、节点和远端会话；在本次受控维护记录中登记恢复记录 ID、核查时间、核查人和结论。当前没有“重放事件”或“恢复完成”API，不应声称调用不存在的命令。

确认本地事务最终未提交后，才可在授权的维护范围内使用已有客户端 `cancel_fill_session(session_uuid)` 撤销那一个远端会话。对于 `cleanup_required=true` 的失败任务也按该精确会话执行。撤销前再次读取远端状态；若已提交或答卷状态与预期不同，先保留证据并交业务负责人判断，不自行删除答卷或患者数据。撤销返回失败时继续保留待处理结论，不伪记为已清理。

任何修改恢复记录、任务状态或执行远端撤销的操作都应记录精确对象、前后状态、操作者和结果；这些是受控维护动作，本说明不会自动执行。不要直接改节点状态、补造任务或删除关联记录来掩盖事务不确定性。
