"""T72 康复临床口径配置中心：禁忌规则集合与签署声明文案。

本模块只承载「可配置的临床口径」：
- 内置通用示例禁忌规则（SAMPLE_RULES）：每条均标注 status="待临床确认"，
  只是规则引擎的结构示例与最小安全兜底，不是任何临床结论；
- 发布签署声明文案（DEFAULT_SIGNATURE_DECLARATION）：默认占位文案，
  status="待临床确认"，上线前必须由临床确认替换；
- 两条口径均可被数据库集合覆盖（运行时可配置、无需改代码）：
  * rehab_clinical_rules —— 规则文档集合；集合存在且有待确认规则时整体
    替换内置示例（覆盖是整集替换，不是合并，避免「内置兜底 + 半份覆盖」
    拼出无人确认过的口径）；
  * rehab_clinical_signature —— 签署声明文档（key=publish_signature）。

覆盖集合读取失败按 fail-closed 处理：口径不可读时宁可拒绝发布，也不在
未知规则状态下放行；单条规则文档结构不合法同样拒绝（静默丢弃坏规则会
把 block 规则变成放行）。

存取动作（读集合 / 读单文档）走公共配置基座 app/core/config_store.py：
本模块的两支读都是 fail-closed（ConfigFail.STRICT），与「运维开关读不到
用默认」的宽松口径刻意分化——基座的 fail 语义是参数，不在这里改写。
"""
from typing import Any, Dict, List

from app.core.config_store import (CONFIG_INVALID, CONFIG_UNAVAILABLE, ConfigFail,
                                   ConfigStore)

# 规则覆盖集合（整集替换内置示例）
RULES_COLLECTION = "rehab_clinical_rules"
# 签署声明覆盖文档集合（key=publish_signature）
SIGNATURE_COLLECTION = "rehab_clinical_signature"
SIGNATURE_KEY = "publish_signature"

RULE_LEVELS = ("warn", "block")
CLINICAL_REVIEW_STATUS = "待临床确认"
RULE_SOURCES = ("builtin-sample", "collection")


# ── 内置通用示例禁忌规则（全部「待临床确认」，仅引擎结构示例）──────────────
# 规则结构（也是 rehab_clinical_rules 集合文档的契约）：
#   rule_id       唯一规则标识
#   level         warn（提示，不阻断）/ block（阻断发布）
#   scope         any / diet / exercise / medication / psychology
#   description   面向医护的规则说明
#   message       命中提示文案（{item_name} 为处方项名占位）
#   when_patient  患者侧条件：allergies_include_any / diagnoses_include_any /
#                 age_below / age_above（全部满足才命中）
#   when_item     处方项侧条件：intervention_types / text_includes_any
#                 （在项名、内容、禁忌、执行说明、药品、食物限制等文本中匹配）
#   allergen_cross_match  true 时：患者任一过敏原字样出现在处方项文本即命中
#                 （患者侧仍可叠加 allergies_include_any 收窄）
SAMPLE_RULES: List[Dict[str, Any]] = [
    {
        "rule_id": "sample-block-penicillin-allergy",
        "level": "block",
        "scope": "medication",
        "description": "患者过敏史含青霉素类字样，且用药处方文本含青霉素类字样（内置示例）",
        "message": "患者过敏史记录含「青霉素」，用药处方「{item_name}」文本含同类字样，发布已被阻断；请人工复核过敏史与处方",
        "when_patient": {"allergies_include_any": ["青霉素"]},
        "allergen_cross_match": True,
        "status": CLINICAL_REVIEW_STATUS,
        "source": "builtin-sample",
    },
    {
        "rule_id": "sample-block-sulfonamide-allergy",
        "level": "block",
        "scope": "medication",
        "description": "患者过敏史含磺胺类字样，且用药处方文本含磺胺类字样（内置示例）",
        "message": "患者过敏史记录含「磺胺」，用药处方「{item_name}」文本含同类字样，发布已被阻断；请人工复核过敏史与处方",
        "when_patient": {"allergies_include_any": ["磺胺"]},
        "allergen_cross_match": True,
        "status": CLINICAL_REVIEW_STATUS,
        "source": "builtin-sample",
    },
    {
        "rule_id": "sample-warn-hypertension-inversion",
        "level": "warn",
        "scope": "exercise",
        "description": "患者诊断含高血压字样，运动处方文本含倒立/头低位/屏气类字样（内置示例）",
        "message": "患者诊断记录含「高血压」，运动处方「{item_name}」含倒立、头低位或屏气类字样，请核实后再发布",
        "when_patient": {"diagnoses_include_any": ["高血压"]},
        "when_item": {"text_includes_any": ["倒立", "头低位", "头低", "屏气", "valsalva"]},
        "status": CLINICAL_REVIEW_STATUS,
        "source": "builtin-sample",
    },
    {
        "rule_id": "sample-warn-diabetes-high-sugar",
        "level": "warn",
        "scope": "diet",
        "description": "患者诊断含糖尿病字样，饮食处方文本含高糖类字样（内置示例）",
        "message": "患者诊断记录含「糖尿病」，饮食处方「{item_name}」含高糖类字样，请核实后再发布",
        "when_patient": {"diagnoses_include_any": ["糖尿病"]},
        "when_item": {"text_includes_any": ["高糖", "蔗糖", "葡萄糖浆"]},
        "status": CLINICAL_REVIEW_STATUS,
        "source": "builtin-sample",
    },
    {
        "rule_id": "sample-warn-elderly-high-load",
        "level": "warn",
        "scope": "exercise",
        "description": "患者年龄超过 70，运动处方文本含大强度/大负重类字样（内置示例）",
        "message": "患者年龄记录超过 70，运动处方「{item_name}」含大强度或大负重类字样，请核实后再发布",
        "when_patient": {"age_above": 70},
        "when_item": {"text_includes_any": ["大强度", "大负重", "极限"]},
        "status": CLINICAL_REVIEW_STATUS,
        "source": "builtin-sample",
    },
]

# 发布签署声明默认文案（「待临床确认」，上线前必须由临床确认替换）
DEFAULT_SIGNATURE_DECLARATION = {
    "declaration": "本人已核对本次发布的康复方案及其全部干预内容，确认内容与患者当前情况相符；"
                   "本签署绑定该发布版本的内容快照哈希，版本一经发布不可修改。",
    "status": CLINICAL_REVIEW_STATUS,
    "source": "builtin",
}


def _text(value):
    return value.strip() if isinstance(value, str) else None


def _string_list(value, field, rule_id):
    if value is None:
        return None
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"rule {rule_id}: {field} must be a non-empty string list")
    return [item.strip() for item in value]


def normalize_rule(doc: Any, source: str) -> Dict[str, Any]:
    """校验并规范化单条规则；结构不合法抛 ValueError（由调用方决定拒绝策略）。"""
    if not isinstance(doc, dict):
        raise ValueError("rule document must be an object")
    rule_id = _text(doc.get("rule_id"))
    if not rule_id:
        raise ValueError("rule_id is required")
    level = _text(doc.get("level"))
    if level not in RULE_LEVELS:
        raise ValueError(f"rule {rule_id}: level must be one of {RULE_LEVELS}")
    scope = _text(doc.get("scope")) or "any"
    if scope not in ("any", "diet", "exercise", "medication", "psychology"):
        raise ValueError(f"rule {rule_id}: unknown scope {scope}")
    description = _text(doc.get("description"))
    message = _text(doc.get("message"))
    if not description or not message or "{item_name}" not in message:
        raise ValueError(f"rule {rule_id}: description and message containing {{item_name}} are required")
    when_patient = doc.get("when_patient") or {}
    if not isinstance(when_patient, dict):
        raise ValueError(f"rule {rule_id}: when_patient must be an object")
    patient = {}
    for key in ("allergies_include_any", "diagnoses_include_any"):
        value = _string_list(when_patient.get(key), f"when_patient.{key}", rule_id)
        if value is not None:
            patient[key] = value
    for key in ("age_below", "age_above"):
        value = when_patient.get(key)
        if value is not None:
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"rule {rule_id}: {key} must be a positive integer")
            patient[key] = value
    when_item = doc.get("when_item") or {}
    if not isinstance(when_item, dict):
        raise ValueError(f"rule {rule_id}: when_item must be an object")
    item = {}
    types = _string_list(when_item.get("intervention_types"), "when_item.intervention_types", rule_id)
    if types is not None:
        unknown = [value for value in types if value not in ("diet", "exercise", "medication", "psychology")]
        if unknown:
            raise ValueError(f"rule {rule_id}: unknown intervention types {unknown}")
        item["intervention_types"] = types
    texts = _string_list(when_item.get("text_includes_any"), "when_item.text_includes_any", rule_id)
    if texts is not None:
        item["text_includes_any"] = [value.lower() for value in texts]
    cross = doc.get("allergen_cross_match")
    if cross is not None and not isinstance(cross, bool):
        raise ValueError(f"rule {rule_id}: allergen_cross_match must be a boolean")
    if not patient and not item and cross is not True:
        raise ValueError(f"rule {rule_id}: a rule must constrain the patient, the item, or cross-match allergies")
    status = _text(doc.get("status")) or CLINICAL_REVIEW_STATUS
    return {"rule_id": rule_id, "level": level, "scope": scope, "description": description,
            "message": message, "when_patient": patient, "when_item": item,
            "allergen_cross_match": cross is True, "status": status, "source": source}


def _rules_error(reason, exc):
    """把基座的失败原因映射为本域错误码（fail-closed：一律 503 拒绝放行）。"""
    from app.core.exceptions import AppBaseException
    if reason == CONFIG_INVALID:
        return AppBaseException("禁忌规则集合存在结构不合法的规则，请修正后再试", status_code=503,
                                error_code="REHAB_CLINICAL_RULES_INVALID")
    return AppBaseException("禁忌规则集合不可读，请稍后重试", status_code=503,
                            error_code="REHAB_CLINICAL_RULES_UNAVAILABLE")


def _signature_error(reason, exc):
    """把基座的失败原因映射为本域错误码（fail-closed：一律 503 拒绝放行）。"""
    from app.core.exceptions import AppBaseException
    if reason == CONFIG_INVALID:
        return AppBaseException("签署声明配置缺少文案，请修正后再试", status_code=503,
                                error_code="REHAB_CLINICAL_SIGNATURE_INVALID")
    return AppBaseException("签署声明配置不可读，请稍后重试", status_code=503,
                            error_code="REHAB_CLINICAL_SIGNATURE_UNAVAILABLE")


def _signature_document(doc: Any) -> Dict[str, Any]:
    """覆盖签署声明的规范化与结构校验（缺文案即内容不合法）。"""
    declaration = _text(doc.get("declaration"))
    if not declaration:
        raise ValueError("签署声明缺少文案")
    return {"declaration": declaration, "status": _text(doc.get("status")) or CLINICAL_REVIEW_STATUS,
            "source": "collection"}


async def load_contraindication_rules(db) -> List[Dict[str, Any]]:
    """读取生效的禁忌规则集合：覆盖集合非空时整集替换内置示例。

    读取失败或单条覆盖规则结构不合法 → 503 fail-closed（规则口径不可读
    或不可信时，禁止在未知规则状态下放行发布）。
    """
    store = ConfigStore(db, RULES_COLLECTION, fail=ConfigFail.STRICT, on_error=_rules_error,
                        validate=lambda doc: normalize_rule(doc, "collection"))
    return await store.read_many({"enabled": {"$ne": False}}, limit=1000,
                                 default=[dict(rule) for rule in SAMPLE_RULES])


async def load_signature_declaration(db) -> Dict[str, Any]:
    """读取发布签署声明：覆盖文档存在且非空时替换默认文案。"""
    store = ConfigStore(db, SIGNATURE_COLLECTION, key_field="key", fail=ConfigFail.STRICT,
                        on_error=_signature_error, validate=_signature_document)
    return await store.read_one(SIGNATURE_KEY, default=dict(DEFAULT_SIGNATURE_DECLARATION))
