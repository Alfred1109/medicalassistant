# 标签唯一性方案（盘点 → 清零 → 维护窗口建索引 → 应用层兜底）

## 背景

开发计划 §14 工程基线复核记录的缺口：标签创建目前「先查重再插入」
（`backend/app/directory/records.py` 的 `create_tag`：`find_one` 命中即
409 `TAG_EXISTS`，否则 `insert_one`），查重与插入之间存在竞态窗口，并发
创建同名同类标签可能产生重复。缺口同时明确：**需先盘点历史数据和确定
迁移方案，再实施约束，不应直接对未知现有数据建唯一索引**。

标签的实现位置（已在代码中核实）：

| 项 | 位置 |
| --- | --- |
| 集合 | `tags`（`app/directory/records.py:22` 等处字面量） |
| 业务唯一键 | `(name, category)`——与 `create_tag` 的查重查询 `{"name": name, "category": category}` 同口径 |
| 文档形状 | `{_id, name(≤40, 落库前 strip), category(≤40, strip), color(≤20), created_at}` |
| 创建路径 | `POST /api/admin/tags`（`app/api/routers/system_admin_router.py:402`）→ `records.create_tag` |
| 删除路径 | `DELETE /api/admin/tags/{id}` → `records.delete_tag`（无更新路径） |
| 权限 | 仅 admin（router `_require_admin`） |
| 引用方式 | 无外键。`health_records.tags`、`organizations.tags` 为自由字符串数组，仅按 name 一维软引用 |

## 第一步：只读盘点

工具：`backend/scripts/label_uniqueness_audit.py`（只读，惯例与
`patient_reference_audit` 一致：URI 参数化、localhost 闸门、JSON 走
stdout、摘要走 stderr、分批游标）。

```bash
cd backend
MONGODB_AUDIT_URI="mongodb://localhost:27017" \
    .venv/bin/python -m scripts.label_uniqueness_audit > tag_audit.json
```

报告口径：

- **重复键组**：同 `(name, category)` 多文档组，附各组 `_id` 清单；
  归组按唯一索引语义——name/category **缺失与 null 同视为 null 键**
  （MongoDB 唯一索引对缺失字段按 null 处理，两者会互撞）。
- **异常形状计数**（建索引前须人工处置）：`missing_*`、`null_*`、
  `blank_*`（strip 后为空）、`unstripped`（带首尾空白，创建路径本会
  strip）、`overlength_*`（超过创建路径上限 40）。
- **软引用悬空**：`health_records.tags` / `organizations.tags` 条目不在
  标签字典 name 中的计数与样本。这是信息性对照而非外键违规。

验收闸门：`duplicate_key_groups` 与全部异常形状计数**归零**后才允许进入
第二步。软引用悬空不阻塞索引，但须业务侧知悉。

## 第二步：清理历史重复（业务决策，工具不代做）

盘点只产出事实清单，重复文档的保留/合并属于业务决策。参考原则：

- 每个重复组保留一条（建议保留最早 `created_at`），其余按 `_id` 删除；
- name/category 缺失、null、未 strip 的异常文档，先补齐/归一化为合法
  形状，再参与唯一性判定；
- 清理后重跑盘点脚本确认归零（可重定向输出留档）。

## 第三步：维护窗口手工建唯一索引

索引规格（与查重口径严格一致，**保持默认 binary collation**，否则应用层
查重与数据库唯一性判定分叉）：

```javascript
db.tags.createIndex(
    { name: 1, category: 1 },
    { name: "uniq_tag_name_category", unique: true }
)
```

- **不进应用启动路径**：`app/db/indexes.py` 不登记该索引，启动流程不改；
  索引由运维在维护窗口手工创建（普通 `createIndex`，存量已清零则建索引
  必然成功）。
- 采用普通唯一索引而非 partial/sparse：创建路径保证 name/category 恒为
  非空字符串，无需排除空值文档；缺值文档属历史异常，已在第一步清零，
  不应被索引排除掩盖。
- 索引名 `uniq_tag_name_category` 与
  `app/directory/records.TAG_UNIQUE_INDEX_NAME` 常量一致（仅作名称约定，
  常量不参与任何索引创建）。

## 第四步：创建路径 11000 兜底（已实施）

`records.create_tag` 已改造为三层（`backend/app/directory/records.py:44`）：

1. 参数校验（422 `INVALID_TAG`）——不变；
2. 友好查重：`find_one({"name","category"})` 命中即 409 `TAG_EXISTS`
   ——保留，常见重复走这条路，错误信息最友好；
3. 兜底：`insert_one` 捕获 `DuplicateKeyError`（11000，唯一索引命中，
   查重-插入竞态），转换为**既有** 409 `TAG_EXISTS` 语义——错误码、
   状态码、响应体不变，既有契约测试断言不放松。

索引未建（第一步至第三步完成前）时第 3 层不会触发，行为与历史完全
等价——改造与建索引互不阻塞，可先合入代码。

## 测试证据

- 单元测试（无 URI）：
  `backend/tests/test_label_uniqueness_audit.py`——盘点逻辑（重复组、
  缺失/null 同键、异常形状、软引用悬空、分批、只读断言、主机闸门）+
  11000 兜底转换 + 无索引时历史行为不变。
- 隔离副本集演练（`REHAB_TEST_TAGS_URI` 门控，未提供自动跳过）：
  `backend/tests/test_tag_uniqueness_replica.py`——合造重复 → 盘点报出
  → 清理归零 → 建索引 → `asyncio.gather` 8 并发创建仅一胜且全部拒绝
  为 409 `TAG_EXISTS` → 不同键创建不受影响；另含无索引对照与缺失/null
  异常形状演练。
- 盘点脚本 CLI 已在本机隔离临时库端到端验证（JSON + 摘要 + 主机闸门），
  临时库已清理；未触碰任何既有库。
