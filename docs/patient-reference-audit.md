# 历史患者引用盘点工具（patient_reference_audit）说明

## 这是什么

`backend/scripts/patient_reference_audit.py` 是患者档案架构第一波段 T6 的
**只读**盘点工具，回答一个问题：当前库里业务集合对患者历史账号
（`users` 集合 `role:"patient"` 文档）的引用，真实存在多少
缺失 / 双形态 / 悬空 / 歧义。它是「处理历史数据：先制定迁移和核实方案」的
第一步——只产出事实清单，**不产出任何迁移或修复决策**，也绝不做迁移或删除。

## 运行方式

在 `backend/` 目录下：

```bash
# JSON 报告重定向到文件，人类可读摘要走 stderr
MONGODB_AUDIT_URI="mongodb://localhost:27017" \
    .venv/bin/python -m scripts.patient_reference_audit > audit.json

# 也可显式指定
.venv/bin/python -m scripts.patient_reference_audit \
    --uri mongodb://localhost:27017 --db <库名> \
    --batch-size 2000 --max-examples 20 > audit.json
```

- 连接串来源优先级：`--uri` > 环境变量 `MONGODB_AUDIT_URI` > `MONGODB_URL`；
  库名来源：`--db` > `MONGODB_DB_NAME` > 连接串默认库。
- **主机闸门**：缺省只允许连 localhost / 127.0.0.1 / ::1；连远程实例必须显式
  加 `--allow-remote`。工具本身无论如何都只读。
- 只读保证：代码路径只调用 `find` + 游标 `to_list`，不存在 insert / update /
  delete / create_index / drop；测试用打桩集合把所有写调用断言为失败。

## 盘点对象

| 集合 | 字段 | 备注 |
| --- | --- | --- |
| followup_records | patient_id | 第二代随访集合 |
| follow_ups | patient_id | 第一代遗留集合（FU01 D-4 决策归档只读、冻结写入）；第一代造数形状文档缺 patient_id 属历史既定（`scripts/migrate_legacy_collections.py` 映射表「不映射项：patient_id」），单独计 `legacy_missing`，详见下方「legacy_followups 对照段」 |
| health_records / health_data / medical_timelines | patient_id | |
| rehab_plans / rehab_plan_versions / rehab_prescription_items / rehab_execution_events / rehab_progress | patient_id | |
| patient_feedback_media | patient_id | |
| devices | patient_id | 历史非患者绑定为 null |
| integration_fill_tasks | patient_id | |
| patientmanager.daily_records | user_id | 注意：真实集合名是带点号的字面量 `patientmanager.daily_records`（`app/api/routers/patient_router.py` 的 `DAILY_RECORDS_COLLECTION`）；新写入用 `str(current_user.id)`；集合存在 string `_id` 的历史文档，router 以 `object:`/`string:` 前缀双形态兼容读取，单独计 `string_id_documents` |
| quality_issues | patient_id | |
| external_patient_links | local_patient_id | 新写入路径会归一为 canonical string（`app/integrations/forms/patient_links.py:97`），历史数据仍可能双形态 |

以上集合名与字段名均已在代码中核实，非凭空清单。另盘 `users` 患者子集：
总数、`is_active` 分布、同 identity key 多文档组、医护归属字段
（`practitioners` / `health_managers`）的形态与悬空。

## 判定口径

与 `app/core/patient_identity.py` 完全一致：

- **identity key**：`ObjectId` 与其 canonical 24 位 hex 字符串同键
  （`identity_key`）；引用值按 key 归组判定，而不是按字面形态比对。
- **悬空**：key 在 `users` 中没有任何文档（无 role 过滤，与
  `load_identity_groups` 命中口径一致）。
- **歧义**：key 命中多个 `users` 文档——即运行时 `LegacyPatientIdentityError`
  （503）的来源。
- **形态计数**：`objectid_form`（BSON ObjectId）/ `string_form`（24 位 hex
  字符串）/ `other_form`（其余字符串、数值等）。other 形态仍参与悬空/歧义
  判定（identity_key 对任意值先做 str 再判定），保证与适配器语义一致。
- **缺失**：`missing`（字段键不存在）与 `null`（字段值为 None，如 devices
  历史非患者绑定）分开计，两者合计即业务语义上的「缺失」。
- **医护归属字段**：条目同样按 identity key 对全部 `users` 判悬空/歧义，
  另给出命中文档的 role 分布（`resolved_roles`，如 `{"doctor": n}`）。

## 部分集合的附加字段

默认字段之外，只有两个集合带附加计数字段（其余集合不出现该键，便于
机读方按字段有无区分口径）：

- **`legacy_missing`（仅 `follow_ups`）**：第一代形状「缺失」（`missing` +
  `null`）计数。第一代造数文档缺 `patient_id` 是迁移脚本映射表明示的
  「不映射项」（无对应来源），属历史既定而非异常，因此不计入悬空口径；
  悬空/歧义仍只统计 `patient_id` 有值且 key 无法唯一命中的文档。
- **`string_id_documents`（仅 `patientmanager.daily_records`）**：`_id` 为
  字符串形态的历史文档计数。router 对记录 ID 采用 `object:`/`string:`
  前缀双形态兼容读取，string `_id` 是已知历史形态，不是脏数据。

## legacy_followups 对照段

顶层 `legacy_followups` 段把两代随访集合的患者引用口径并列输出，便于
直接对照第一代遗留集合与第二代业务集合的悬空/歧义规模：

```json
"legacy_followups": {
  "note": "……第一代缺 patient_id 属历史既定……",
  "first_generation":  { "collection": "follow_ups",        "...同 collections 段字段": 0, "legacy_missing": 0 },
  "second_generation": { "collection": "followup_records",  "...同 collections 段字段": 0 }
}
```

- `first_generation` / `second_generation` 是 `collections` 中对应统计段的
  原样引用（附 `collection` 名称键），数字与逐集合段完全一致，不产生
  第二份独立计数。
- 解读规则：第一代 `missing`/`null`/`legacy_missing` 属预期，不需治理；
  两代的 `dangling`/`ambiguous` 才是需要人工核实的部分。

## 如何解读结果

- `dangling > 0`：存在指向不存在患者的引用。迁移前须核实是脏数据、已删账号
  还是引用形态问题。
- `ambiguous > 0`：这些患者账号本身在 `users` 里存在同 key 多文档，运行时
  相关患者接口会 503。结合 `users_patients.duplicate_identity_groups` 的
  key 与 `_id` 清单逐组人工核实，是歧义治理的直接输入。
- 双形态计数只反映写入历史；`identity_key` 已使两种形态运行时等价，形态
  本身不是故障，但同名两份（ambiguous）是。
- `missing`/`null` 集中在 `follow_ups`（已计入其 `legacy_missing`，属历史
  既定，见 `legacy_followups` 对照段）；若出现在 `followup_records` 等业务
  集合则须单独核实。
- 大集合用 `--batch-size` 分批游标处理，内存不随集合大小线性膨胀；样本
  （`*_examples`）按 key 去重并默认截断在 20 条，`examples_truncated` 标记
  是否截断。

## 与迁移方案的关系

本工具只提供盘点事实，**不产出迁移决策**。是否合并同 key 多文档、是否清理
悬空引用、是否归一引用形态，均属业务决策，须另行制定迁移与核实方案、经业务
确认并在隔离实例演练后执行（同 `scripts/migrate_legacy_collections.py` 的
行为约束：任何真实迁移执行前必须业务确认）。

## 测试

`backend/tests/test_patient_reference_audit.py`（内存打桩集合，不依赖真实
MongoDB）覆盖：双形态归并计数、悬空、歧义、缺失/null、空集合与不存在集合、
分批边界（25 条 / batch=10）、users 患者 is_active 分布与同 key 组清单、
医护归属字段悬空、只读保证（写调用即失败）、主机闸门、follow_ups 第一代
缺 patient_id 的 `legacy_missing` 与 `legacy_followups` 对照段、
`patientmanager.daily_records` 的 string `_id` 计数与 `user_id` 双形态/悬空。

```bash
DEBUG=false .venv/bin/python -m pytest tests/test_patient_reference_audit.py -q
```
