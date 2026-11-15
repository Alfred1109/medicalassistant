"""T74 设备接入网关测试用内存假库（模拟 motor 常用子集）。

仅实现 device_ingestion_service / device_protocol 测试所需的操作：
insert_one / find_one / find(sort→limit→to_list) / update_one($set/$unset/$inc，
$set 支持点路径含列表下标，覆盖 rehabilitation_service.log_exercise_progress
的 exercises.{i} 写法) / to_list(None)。
匹配支持等值、$ne/$gte/$lte/$in 与点路径（metadata.source）。
"""
from copy import deepcopy
from datetime import datetime


def _resolve_path(doc, path):
    parts = path.split(".")
    node = doc
    for part in parts:
        if isinstance(node, list):
            try:
                node = node[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(node, dict):
            node = node.get(part)
        else:
            return None
        if node is None and part != parts[-1]:
            return None
    return node


def _set_path(doc, path, value):
    parts = path.split(".")
    node = doc
    for part in parts[:-1]:
        if isinstance(node, list):
            node = node[int(part)]
        else:
            node = node.setdefault(part, {})
    last = parts[-1]
    if isinstance(node, list):
        node[int(last)] = value
    else:
        node[last] = value


def _unset_path(doc, path):
    parts = path.split(".")
    node = doc
    for part in parts[:-1]:
        node = node[part] if isinstance(node, dict) else node[int(part)]
    if isinstance(node, dict):
        node.pop(parts[-1], None)


def _match(doc, query):
    for key, cond in query.items():
        value = _resolve_path(doc, key)
        if isinstance(cond, dict) and cond and all(
                k.startswith("$") for k in cond):
            for op, target in cond.items():
                if op == "$ne" and value == target:
                    return False
                if op == "$gte" and (value is None or value < target):
                    return False
                if op == "$lte" and (value is None or value > target):
                    return False
                if op == "$in" and value not in target:
                    return False
                if op not in ("$ne", "$gte", "$lte", "$in"):
                    raise NotImplementedError(f"假库未实现操作符 {op}")
        else:
            if value != cond:
                return False
    return True


class FakeInsertResult:
    def __init__(self, inserted_id):
        self.inserted_id = inserted_id


class FakeUpdateResult:
    def __init__(self, matched_count, modified_count):
        self.matched_count = matched_count
        self.modified_count = modified_count


class FakeQuery:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, field, direction=1):
        self._docs = sorted(
            self._docs,
            key=lambda d: (d.get(field) is None, d.get(field)),
            reverse=direction < 0)
        return self

    def limit(self, n):
        self._limit = n
        return self

    async def to_list(self, n=None):
        cap = n if n else getattr(self, "_limit", None)
        docs = self._docs
        if cap:
            docs = docs[:cap]
        return deepcopy(docs)


class FakeCollection:
    def __init__(self):
        self.docs = []

    async def insert_one(self, doc):
        doc = deepcopy(doc)
        doc["_id"] = doc.get("_id")
        self.docs.append(doc)
        return FakeInsertResult(doc["_id"])

    async def find_one(self, query):
        for doc in self.docs:
            if _match(doc, query):
                return deepcopy(doc)
        return None

    def find(self, query):
        return FakeQuery([deepcopy(d) for d in self.docs if _match(d, query)])

    async def update_one(self, query, update):
        matched = modified = 0
        for doc in self.docs:
            if not _match(doc, query):
                continue
            matched += 1
            for path, value in (update.get("$set") or {}).items():
                _set_path(doc, path, deepcopy(value))
            for path, _ in (update.get("$unset") or {}).items():
                _unset_path(doc, path)
            for path, delta in (update.get("$inc") or {}).items():
                current = _resolve_path(doc, path) or 0
                _set_path(doc, path, current + delta)
            modified += 1
        return FakeUpdateResult(matched, modified)

    async def count_documents(self, query):
        return sum(1 for d in self.docs if _match(d, query))


class FakeDatabase:
    def __init__(self, collections=()):
        self._collections = {name: FakeCollection()
                             for name in collections}

    def __getitem__(self, name):
        return self._collections.setdefault(name, FakeCollection())

    def __getattr__(self, name):
        return self[name]

    def seed(self, name, docs):
        self[name].docs.extend(deepcopy(docs))


def silent_analysis_mock():
    """device_analysis_service 打桩：generate_device_alerts 返回空预警。"""
    from unittest.mock import AsyncMock
    mock = AsyncMock()
    mock.generate_device_alerts = AsyncMock(return_value=[])
    return mock
