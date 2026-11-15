# 随访完成率的统一读取口径

状态枚举、历史别名和统计语义统一在 `backend/app/core/followup_semantics.py`；
`schemas.followup.FollowUpStatus` 保留兼容导入。历史别名只影响读取和统计，
不增加节点写入或状态流转许可。

当前只支持 `conservative_non_void`，**待临床确认**：

- `completed`（含历史 `done`、`finished`）计为完成。
- `canceled`（含历史 `cancelled`、`void`）作为作废记录排除分母。
- 其他状态，包括待审阅、未终态、未知、缺失和无效状态，计入分母但不计完成。
- 分母为零时结果为无法计算，不用 0 代替。
- `pending` 作为历史待安排状态展示，不计完成。

ICF 与过程质控调用同一计算函数，均返回分子、分母、作废排除数和口径说明。
ICF 仍通过随访领域服务读取数据，只读投影保留原始状态以兼容历史/未知值；
软删除记录排除，保留代码实际既有的计划时间升序前 500 条采样，包括 Mongo 空值排序；
不新增 ID 次序，保持原有同时间值的排序行为。旧注释称「最近 500 条」与实现不符，
此处只修正说明，不改变取样事实。是否改为最近 500 条须另行确认。
过程质控按当前授权和日期筛选的全部记录统计。因此公式一致并不表示两个页面的
统计范围一致；页面和 CSV 均说明各自范围。

配置沿用 `icf_metric_configs` 中 `followup_completion_rate.params`，由现有
`PUT /icf/metric-configs/followup_completion_rate` 接口维护：

```json
{"params":{"min_rate":0.8,"completion_policy":"conservative_non_void"}}
```

旧配置缺少 `completion_policy` 时使用同一保守默认，读取时回显有效配置，
无需改写历史文档。`min_rate` 必须是 0 到 1 之间的有限数值；ICF 页面可修改并保存。
没有经确认的其他公式，未知策略一律拒绝，不自动猜测或切换。此技术口径不代表
已经取得临床认可，不改变随访节点事实或审核结果。
