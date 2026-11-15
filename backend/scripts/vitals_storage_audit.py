"""生命体征落点冗余只读盘点工具。

盘什么：
  生命体征的三个落点存量与相互重叠——
    ① health_data 集合（医护/患者手工录入，data.type 记指标类型）
    ② device_data 集合（设备采集与设备手工登记，data_type 记指标类型）
    ③ health_records 内嵌 vital_signs（列表）
  外加两个旁证面：medical_timelines 时间线对三类数据的覆盖缺口、
  health_metrics 孤儿集合（只读不写）。

为什么盘：生命体征要收敛为单一事实源（health_data），device_data 降级为
设备原始遥测留档，内嵌 vital_signs 改为读取投影。收敛前必须先知道存量
重叠量、时间线缺口与手工登记数据的患者归属缺失，否则去重口径无从谈起。
本工具只产出事实清单，不产出清理决策，也绝不写库。

本工具只读：仅执行 find / to_list / count_documents 读取，绝不 insert /
update / delete / create_index / drop。连接串经 --uri 参数或 MONGODB_AUDIT_URI
（缺省回退 MONGODB_URL）环境变量提供；缺省只允许连接
localhost / 127.0.0.1 / ::1，连远程实例必须显式加 --allow-remote
（虽然本工具不写，仍做主机闸门）。惯例与 scripts/patient_reference_audit.py
一致。

运行方式（在 backend/ 目录下）：
    MONGODB_AUDIT_URI="mongodb://localhost:27017" \
        .venv/bin/python -m scripts.vitals_storage_audit > vitals.json
    .venv/bin/python -m scripts.vitals_storage_audit \
        --uri mongodb://localhost:27017 --db rehabman --batch-size 2000 \
        --overlap-window-hours 24 > vitals.json

输出：JSON 报告写 stdout（可重定向），人类可读摘要写 stderr。

输出字段含义（JSON 顶层）：
  generated_at          ISO8601 生成时间
  database              盘点的库名
  batch_size            游标分批大小
  overlap_window_hours  重叠判定的时间窗（同患者同指标两条读数相差在此窗内视为可能重复）
  health_data           落点①：手工录入的体征数据
    total_documents     集合内扫描到的文档总数
    by_data_type        data_type 分布（vital_sign / lab_result / …）
    by_source           source 分布（manual / device / imported）
    vital_by_type       data_type=vital_sign 时按 data.type 的指标分布
    missing_patient_id  缺 patient_id 的文档数（归属缺失，无法进入任何按患者查询）
    missing_recorded_at 缺 recorded_at 的文档数（时间线排序与重叠判定都受影响）
    time_range          recorded_at 的最小/最大（可解析的那些）
  device_data           落点②：设备原始遥测
    total_documents     集合内扫描到的文档总数
    by_data_type        data_type 分布
    by_source           metadata.source 分布（采集适配器 / 手工登记）
    missing_patient_id  缺 patient_id 的文档数。手工登记路径
                        （device_service.record_manual_reading）只写 device_id
                        不写 patient_id，因此这些读数无法直接归属到患者
    missing_timestamp   缺 timestamp 的文档数
    time_range          timestamp 的最小/最大（可解析的那些）
  health_records_embedded 落点③：health_records 内嵌 vital_signs
    total_documents     集合内扫描到的文档总数
    documents_with_vital_signs 含非空 vital_signs 的文档数
    entries             vital_signs 条目总数
    by_type             条目按 type 字段的分布
  medical_timelines     时间线覆盖
    total_documents     集合内扫描到的文档总数
    by_item_type        item_type 分布（health_data_vital_sign / health_record / follow_up …）
    vital_sign_entries  item_type=health_data_vital_sign 的条目数
    linked_health_data  related_ids 能对上 health_data 的条目数
    device_linked_entries 能对上 device_data 的条目数（设备采集不进时间线，
                        这是覆盖缺口的直接证据）
  health_metrics        孤儿集合
    total_documents     集合内文档数（应用只读不写）
  overlap               落点①与落点②的重叠估算
    matched_pairs       同患者同指标、时间差在窗口内的读数对数
    patients            存在重叠的患者数
    by_metric           按指标的配对数
    unmatched_device    设备侧读数中无法参与比对的数量（缺 patient_id 或指标不可归一）
    examples            配对样本（默认最多 20 条）
"""

import argparse
import asyncio
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from urllib.parse import urlsplit

BATCH_SIZE_DEFAULT = 2000
MAX_EXAMPLES_DEFAULT = 20
OVERLAP_WINDOW_HOURS_DEFAULT = 24
_ALLOWED_HOSTS = {"localhost", "127.0.0.1", "::1"}

_METRIC_ALIASES = {
    "hr": "heart_rate",
    "heartrate": "heart_rate",
    "pulse": "heart_rate",
    "bp": "blood_pressure",
    "bloodpressure": "blood_pressure",
    "abp": "blood_pressure",
    "glu": "blood_glucose",
    "bloodglucose": "blood_glucose",
    "glucose": "blood_glucose",
    "temp": "temperature",
    "body_temperature": "temperature",
}


def _norm_metric(name):
    if not isinstance(name, str):
        return ""
    key = name.strip().lower().replace("-", "_").replace(" ", "_")
    return _METRIC_ALIASES.get(key, key)


def _as_datetime(value):
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value:
        text = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _doc_id(doc):
    value = doc.get("_id")
    return str(value) if value is not None else ""


async def _stream(collection, projection, batch_size):
    # projection 必须作为 find 的第二个位置参数；放第一个会被当成过滤条件
    cursor = collection.find({}, projection)
    while True:
        batch = await cursor.to_list(length=batch_size)
        if not batch:
            break
        for doc in batch:
            yield doc
        if len(batch) < batch_size:
            break


async def audit_database(db, batch_size=BATCH_SIZE_DEFAULT,
                         max_examples=MAX_EXAMPLES_DEFAULT,
                         overlap_window_hours=OVERLAP_WINDOW_HOURS_DEFAULT):
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "database": db.name,
        "batch_size": batch_size,
        "overlap_window_hours": overlap_window_hours,
    }

    health_data = await _audit_health_data(db, batch_size)
    device_data = await _audit_device_data(db, batch_size)
    embedded = await _audit_embedded(db, batch_size)
    timelines = await _audit_timelines(db, batch_size)
    health_metrics = await _audit_health_metrics(db)

    overlap = _overlap(health_data, device_data, overlap_window_hours,
                       max_examples)
    health_data_ids = health_data.pop("_ids")
    device_data_ids = device_data.pop("_ids")
    health_data.pop("_readings")
    device_data.pop("_readings")
    timelines["linked_health_data"] = sum(
        1 for doc_id in timelines["_related_health_data"]
        if doc_id in health_data_ids)
    timelines["device_linked_entries"] = sum(
        1 for doc_id in timelines["_related_device_data"]
        if doc_id in device_data_ids)
    timelines.pop("_related_health_data")
    timelines.pop("_related_device_data")

    report["health_data"] = health_data
    report["device_data"] = device_data
    report["health_records_embedded"] = embedded
    report["medical_timelines"] = timelines
    report["health_metrics"] = health_metrics
    report["overlap"] = overlap
    return report


async def _audit_health_data(db, batch_size):
    by_data_type = Counter()
    by_source = Counter()
    vital_by_type = Counter()
    missing_patient_id = 0
    missing_recorded_at = 0
    time_min = None
    time_max = None
    ids = set()
    readings = []

    async for doc in _stream(db["health_data"], {
            "patient_id": 1, "data_type": 1, "source": 1, "recorded_at": 1,
            "data.type": 1, "data.value": 1}, batch_size):
        ids.add(_doc_id(doc))
        by_data_type[doc.get("data_type") or "(缺失)"] += 1
        by_source[doc.get("source") or "(缺失)"] += 1
        if not doc.get("patient_id"):
            missing_patient_id += 1
        recorded_at = _as_datetime(doc.get("recorded_at"))
        if recorded_at is None:
            missing_recorded_at += 1
        else:
            time_min = recorded_at if time_min is None or recorded_at < time_min else time_min
            time_max = recorded_at if time_max is None or recorded_at > time_max else time_max
        if doc.get("data_type") == "vital_sign":
            data = doc.get("data") if isinstance(doc.get("data"), dict) else {}
            metric = _norm_metric(data.get("type"))
            vital_by_type[metric or "(缺失)"] += 1
            if metric and recorded_at and doc.get("patient_id"):
                readings.append({
                    "id": _doc_id(doc),
                    "patient_id": str(doc.get("patient_id")),
                    "metric": metric,
                    "at": recorded_at,
                })

    return {
        "total_documents": len(ids),
        "by_data_type": dict(by_data_type),
        "by_source": dict(by_source),
        "vital_by_type": dict(vital_by_type),
        "missing_patient_id": missing_patient_id,
        "missing_recorded_at": missing_recorded_at,
        "time_range": {"min": time_min.isoformat() if time_min else None,
                       "max": time_max.isoformat() if time_max else None},
        "_readings": readings,
        "_ids": ids,
    }


async def _audit_device_data(db, batch_size):
    by_data_type = Counter()
    by_source = Counter()
    missing_patient_id = 0
    missing_timestamp = 0
    time_min = None
    time_max = None
    ids = set()
    readings = []

    async for doc in _stream(db["device_data"], {
            "patient_id": 1, "device_id": 1, "data_type": 1, "timestamp": 1,
            "metadata.source": 1}, batch_size):
        ids.add(_doc_id(doc))
        by_data_type[doc.get("data_type") or "(缺失)"] += 1
        metadata = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
        by_source[metadata.get("source") or "(缺失)"] += 1
        if not doc.get("patient_id"):
            missing_patient_id += 1
        timestamp = _as_datetime(doc.get("timestamp"))
        if timestamp is None:
            missing_timestamp += 1
        else:
            time_min = timestamp if time_min is None or timestamp < time_min else time_min
            time_max = timestamp if time_max is None or timestamp > time_max else time_max
        metric = _norm_metric(doc.get("data_type"))
        if metric and timestamp and doc.get("patient_id"):
            readings.append({
                "id": _doc_id(doc),
                "patient_id": str(doc.get("patient_id")),
                "metric": metric,
                "at": timestamp,
            })

    return {
        "total_documents": len(ids),
        "by_data_type": dict(by_data_type),
        "by_source": dict(by_source),
        "missing_patient_id": missing_patient_id,
        "missing_timestamp": missing_timestamp,
        "time_range": {"min": time_min.isoformat() if time_min else None,
                       "max": time_max.isoformat() if time_max else None},
        "_readings": readings,
        "_ids": ids,
    }


async def _audit_embedded(db, batch_size):
    total = 0
    with_vitals = 0
    entries = 0
    by_type = Counter()

    async for doc in _stream(db["health_records"], {"vital_signs": 1}, batch_size):
        total += 1
        vitals = doc.get("vital_signs")
        if not isinstance(vitals, list) or not vitals:
            continue
        with_vitals += 1
        for item in vitals:
            entries += 1
            if isinstance(item, dict):
                by_type[_norm_metric(item.get("type")) or "(缺失)"] += 1
            else:
                by_type["(非对象)"] += 1

    return {
        "total_documents": total,
        "documents_with_vital_signs": with_vitals,
        "entries": entries,
        "by_type": dict(by_type),
    }


async def _audit_timelines(db, batch_size):
    total = 0
    by_item_type = Counter()
    vital_sign_entries = 0
    related_health = set()
    related_device = set()

    async for doc in _stream(db["medical_timelines"], {
            "patient_id": 1, "item_type": 1, "related_ids": 1}, batch_size):
        total += 1
        item_type = doc.get("item_type") or "(缺失)"
        by_item_type[item_type] += 1
        if item_type == "health_data_vital_sign":
            vital_sign_entries += 1
        related = doc.get("related_ids")
        if isinstance(related, list):
            for item in related:
                if isinstance(item, str):
                    related_health.add(item)
                elif item is not None:
                    related_health.add(str(item))
                    related_device.add(str(item))

    return {
        "total_documents": total,
        "by_item_type": dict(by_item_type),
        "vital_sign_entries": vital_sign_entries,
        "_related_health_data": related_health,
        "_related_device_data": related_device,
    }


async def _audit_health_metrics(db):
    return {"total_documents": await db["health_metrics"].count_documents({})}


def _overlap(health_data, device_data, window_hours, max_examples):
    window_seconds = window_hours * 3600
    by_key = defaultdict(list)
    for reading in device_data["_readings"]:
        by_key[(reading["patient_id"], reading["metric"])].append(reading)

    matched = 0
    patients = set()
    by_metric = Counter()
    examples = []
    for reading in health_data["_readings"]:
        candidates = by_key.get((reading["patient_id"], reading["metric"]), ())
        for candidate in candidates:
            delta = abs((reading["at"] - candidate["at"]).total_seconds())
            if delta > window_seconds:
                continue
            matched += 1
            patients.add(reading["patient_id"])
            by_metric[reading["metric"]] += 1
            if len(examples) < max_examples:
                examples.append({
                    "patient_id": reading["patient_id"],
                    "metric": reading["metric"],
                    "health_data_id": reading["id"],
                    "device_data_id": candidate["id"],
                    "delta_hours": round(delta / 3600, 2),
                })
            break

    return {
        "window_hours": window_hours,
        "matched_pairs": matched,
        "patients": len(patients),
        "by_metric": dict(by_metric),
        "unmatched_device": len(device_data["_readings"]),
        "examples": examples,
        "examples_truncated": matched > len(examples),
    }


def render_summary(report):
    health = report["health_data"]
    device = report["device_data"]
    embedded = report["health_records_embedded"]
    timelines = report["medical_timelines"]
    overlap = report["overlap"]
    lines = [
        f"库 {report['database']}：体征落点盘点（重叠窗 {report['overlap_window_hours']}h）",
        f"  health_data     {health['total_documents']} 条；缺 patient_id {health['missing_patient_id']}，"
        f"缺 recorded_at {health['missing_recorded_at']}；vital_sign {sum(health['vital_by_type'].values())} 条",
        f"  device_data     {device['total_documents']} 条；缺 patient_id {device['missing_patient_id']}，"
        f"缺 timestamp {device['missing_timestamp']}",
        f"  内嵌 vital_signs {embedded['entries']} 条，分布在 {embedded['documents_with_vital_signs']} 份 health_records",
        f"  medical_timelines {timelines['total_documents']} 条；vital_sign 条目 {timelines['vital_sign_entries']}；"
        f"对上 health_data {timelines['linked_health_data']}，对上 device_data {timelines['device_linked_entries']}",
        f"  health_metrics  {report['health_metrics']['total_documents']} 条（应用只读）",
        f"  重叠配对 {overlap['matched_pairs']} 对，涉及 {overlap['patients']} 名患者；"
        f"明细 {json.dumps(overlap['by_metric'], ensure_ascii=False)}",
    ]
    return "\n".join(lines)


def check_host_allowed(uri, allow_remote):
    host = (urlsplit(uri).hostname or "").lower()
    if not host:
        raise SystemExit("无法从连接串解析主机名；请检查 --uri / MONGODB_AUDIT_URI")
    if host not in _ALLOWED_HOSTS and not allow_remote:
        raise SystemExit(
            f"目标主机 {host} 不在 localhost 白名单内；本工具默认仅允许本机。"
            "确需连远程实例请显式加 --allow-remote（工具仍只读）。")


async def run(uri, db_name, batch_size, max_examples, overlap_window_hours,
              allow_remote):
    check_host_allowed(uri, allow_remote)
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient(uri)
    try:
        db = client[db_name] if db_name else client.get_default_database()
        report = await audit_database(db, batch_size=batch_size,
                                      max_examples=max_examples,
                                      overlap_window_hours=overlap_window_hours)
    finally:
        client.close()
    return report


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="生命体征落点冗余只读盘点（绝不写库）")
    parser.add_argument("--uri", default=os.environ.get("MONGODB_AUDIT_URI")
                        or os.environ.get("MONGODB_URL"),
                        help="MongoDB 连接串；缺省读 MONGODB_AUDIT_URI / MONGODB_URL")
    parser.add_argument("--db", default=os.environ.get("MONGODB_DB_NAME"),
                        help="库名；缺省读 MONGODB_DB_NAME 或连接串默认库")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE_DEFAULT)
    parser.add_argument("--max-examples", type=int, default=MAX_EXAMPLES_DEFAULT)
    parser.add_argument("--overlap-window-hours", type=float,
                        default=OVERLAP_WINDOW_HOURS_DEFAULT,
                        help="同患者同指标两条读数相差多少小时内视为可能重复")
    parser.add_argument("--allow-remote", action="store_true",
                        help="允许连接非 localhost 主机（工具仍只读）")
    args = parser.parse_args(argv)
    if not args.uri:
        raise SystemExit("缺连接串：用 --uri 或环境变量 MONGODB_AUDIT_URI / MONGODB_URL")
    return args


def main(argv=None):
    args = parse_args(argv)
    report = asyncio.run(run(args.uri, args.db, args.batch_size,
                             args.max_examples, args.overlap_window_hours,
                             args.allow_remote))
    json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    sys.stderr.write(render_summary(report) + "\n")


if __name__ == "__main__":
    main()
