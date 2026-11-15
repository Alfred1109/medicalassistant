"""配置存取基座（W2-E；批次 4 第 1 项「ConfigStore 统一」）。

仓库里有 6+ 种配置存储模式，差异集中在三处：**集合名**、**文档形状**、
**读不到时的兜底语义**。差异本身是业务事实（临床口径与运维开关的兜底
口径本就不同），必须保留；需要收敛的是「从配置集合读一份/一组配置」与
「写一份配置」这层存取动作。

本模块只做这件事，并把**读失败语义做成参数**：

- `ConfigFail.STRICT`（fail-closed）：读失败（传输错误）或内容不合法一律
  抛错——口径不可读时宁可拒绝业务，也不在未知配置下放行；
- `ConfigFail.SOFT`（fail-soft）：读失败时回落到内置默认值，绝不假装读到
  了配置。

**两种语义是刻意分化的业务决定，不得一刀切**：临床口径（禁忌规则、发布
签署声明）读不到就不能放行；运维开关读不到可以先用默认值继续服务。

「集合里没有覆盖文档」不是失败——那是「未配置」状态，一律回落到内置默认
值，与 `fail` 参数无关。

错误码仍属各配置域契约：基座只给出失败**原因**（`CONFIG_UNAVAILABLE` /
`CONFIG_INVALID`），由调用方经 `on_error` 映射成自己的错误码与错误类型。
"""
from enum import Enum

# 读失败原因（由 on_error 映射为各配置域自己的错误码）
CONFIG_UNAVAILABLE = "unavailable"
CONFIG_INVALID = "invalid"


class ConfigFail(str, Enum):
    """读失败语义。"""

    STRICT = "strict"   # fail-closed：读失败/内容不合法 → 抛错
    SOFT = "soft"       # fail-soft：读失败/内容不合法 → 回落默认值


class ConfigStore:
    """按集合承载配置读写的存取基座。

    - collection：配置集合名；
    - key_field：单文档配置的定位字段（默认 "_id"）；
    - fail：读失败语义（`ConfigFail.STRICT` / `ConfigFail.SOFT`）；
    - on_error：`(reason, exc) -> Exception` 工厂，把失败原因映射成本域错误码；
      省略时原样抛出底层异常。
    - validate：可选的内容校验/规范化回调 `(document) -> document`，抛 `ValueError`
      即视为内容不合法（`CONFIG_INVALID`）。
    """

    def __init__(self, db, collection, *, key_field="_id", fail=ConfigFail.STRICT,
                 on_error=None, validate=None):
        self.db = db
        self.collection = db[collection]
        self.key_field = key_field
        self.fail = fail
        self.on_error = on_error
        self.validate = validate

    async def read_one(self, key, *, default=None):
        """读一份配置文档。

        集合里没有该文档 → 返回 `default`（未配置状态，不是失败）；
        读失败或内容不合法 → 按 `fail` 语义处理。
        """
        try:
            document = await self.collection.find_one({self.key_field: key})
        except Exception as exc:
            return self._failed(CONFIG_UNAVAILABLE, exc, default)
        if document is None:
            return default
        return self._validated(document, default)

    async def read_many(self, query=None, *, limit=1000, default=None):
        """读一组配置文档。

        没有覆盖文档 → 返回 `default`（未配置状态，不是失败）；
        读失败或任一文档内容不合法 → 按 `fail` 语义处理。
        """
        try:
            documents = await self.collection.find(query or {}).to_list(length=limit)
        except Exception as exc:
            return self._failed(CONFIG_UNAVAILABLE, exc, default)
        if not documents:
            return default
        if self.validate is None:
            return documents
        try:
            return [self.validate(document) for document in documents]
        except ValueError as exc:
            return self._failed(CONFIG_INVALID, exc, default)

    async def write(self, key, document, *, upsert=True):
        """按 `key_field` 写入一份配置（默认 upsert），返回写入的字段。

        定位键只进过滤条件不进 `$set`（`_id` 不可更新）；upsert 时由过滤条件
        提供文档主键。
        """
        await self.collection.update_one({self.key_field: key}, {"$set": document},
                                          upsert=upsert)
        return document

    def _validated(self, document, default):
        if self.validate is None:
            return document
        try:
            return self.validate(document)
        except ValueError as exc:
            return self._failed(CONFIG_INVALID, exc, default)

    def _failed(self, reason, exc, default):
        """按 fail 语义处理失败：严格抛错，宽松回落默认值。"""
        if self.fail is ConfigFail.SOFT:
            return default
        if self.on_error is None:
            raise exc
        raise self.on_error(reason, exc) from exc
