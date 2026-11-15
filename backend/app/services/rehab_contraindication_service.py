"""T72 康复禁忌规则引擎：纯函数实现，便于测试，不触库、不发请求。

规则来源与口径见 rehab_clinical_config.py；本模块只负责匹配判定：
- build_patient_context：把患者文档（legacy users 文档或 canonical
  clinical_patients 文档，两者医学字段同构：medical_info / diagnosis /
  allergies / age）规约成规则引擎可判定的上下文；
- item_search_text：把处方项的可检索文本拼平（项名、内容、禁忌、适用条件、
  患者执行说明、药品引用、食物限制、疗程说明）；
- evaluate_contraindications：按规则逐条匹配（患者侧条件全部满足 且
  处方项侧条件满足；allergen_cross_match 规则以患者过敏原字样在处方项
  文本中出现为命中）；warn/block 均只产出 finding，是否阻断由调用方决定。
"""
import re
from typing import Any, Dict, List

# 患者诊断/过敏原文本常见分隔符（不做医学解析，只做文本切分）
_SEPARATORS = re.compile(r"[，,、;；/／\n\r]")


def _split_text(value) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        parts: List[str] = []
        for entry in value:
            parts.extend(_split_text(entry))
        return parts
    if not isinstance(value, str):
        return []
    return [part.strip() for part in _SEPARATORS.split(value) if part.strip()]


def _dict(value) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def build_patient_context(patient_doc: Dict[str, Any]) -> Dict[str, Any]:
    """从患者文档提取规则引擎上下文（缺项如实留空，不推断临床数据）。"""
    doc = patient_doc if isinstance(patient_doc, dict) else {}
    medical = _dict(doc.get("medical_info"))
    demographic = _dict(doc.get("demographic_info"))
    diagnoses = []
    for source in (medical.get("diagnosis"), medical.get("condition"), doc.get("diagnosis")):
        diagnoses.extend(_split_text(source))
    allergies = []
    for source in (doc.get("allergies"), medical.get("allergies")):
        allergies.extend(_split_text(source))
    age = doc.get("age")
    if age is None:
        age = demographic.get("age")
    if isinstance(age, bool) or not isinstance(age, (int, float)):
        age = None
    gender = doc.get("gender") or demographic.get("gender")
    return {"diagnoses": diagnoses, "allergies": allergies,
            "diagnosis_text": " ".join(diagnoses).lower(),
            "age": age, "gender": gender if isinstance(gender, str) else None}


def item_search_text(item: Dict[str, Any]) -> str:
    """处方项可检索文本：规则文本匹配的输入面（全部为处方项自身字段）。"""
    item = item if isinstance(item, dict) else {}
    medication = _dict(item.get("medication_fields"))
    diet = _dict(item.get("diet_fields"))
    psychology = _dict(item.get("psychology_fields"))
    course = _dict(item.get("course"))
    pieces = [item.get("name"), item.get("description"), item.get("patient_instructions"),
              medication.get("drug_ref"), medication.get("frequency"), medication.get("route"),
              diet.get("meal_structure_ref"), psychology.get("modality_ref"), course.get("note")]
    for source in (item.get("contraindications"), item.get("applicability_conditions"),
                   item.get("execution_requirements"), item.get("diet_fields") and diet.get("food_restrictions"),
                   medication.get("monitoring")):
        pieces.extend(_split_text(source))
    return " ".join(str(piece) for piece in pieces if piece).lower()


def _contains_any(terms: List[str], entries: List[str]) -> bool:
    """双向子串包含（大小写不敏感）：过敏史「青霉素」匹配记录「青霉素过敏」。"""
    lowered = [entry.lower() for entry in entries if isinstance(entry, str)]
    return any(term.lower() in entry or entry in term.lower() for term in terms for entry in lowered)


def _patient_matches(rule: Dict[str, Any], context: Dict[str, Any]) -> bool:
    when = rule.get("when_patient") or {}
    for term in when.get("allergies_include_any") or []:
        if not _contains_any([term], context.get("allergies") or []):
            return False
    for term in when.get("diagnoses_include_any") or []:
        if term.lower() not in context.get("diagnosis_text", ""):
            return False
    age = context.get("age")
    for key, ok in (("age_below", lambda value, bound: value < bound),
                    ("age_above", lambda value, bound: value > bound)):
        bound = when.get(key)
        if bound is not None and (age is None or not ok(age, bound)):
            return False
    return True


def _item_matches(rule: Dict[str, Any], item: Dict[str, Any], context: Dict[str, Any]) -> bool:
    scope = rule.get("scope") or "any"
    if scope != "any" and item.get("intervention_type") != scope:
        return False
    when = rule.get("when_item") or {}
    types = when.get("intervention_types")
    if types and item.get("intervention_type") not in types:
        return False
    text_terms = when.get("text_includes_any")
    if text_terms:
        text = item_search_text(item)
        if not any(term.lower() in text for term in text_terms):
            return False
    if rule.get("allergen_cross_match"):
        # 交叉匹配语义：患者过敏记录（或规则声明的过敏原字样）任一出现在
        # 处方项文本即命中；患者无过敏记录时不命中（不用空过敏史猜规则）。
        allergies = context.get("allergies") or []
        if not allergies:
            return False
        terms = [str(term) for term in ((rule.get("when_patient") or {}).get("allergies_include_any") or [])]
        terms += [str(allergy) for allergy in allergies]
        text = item_search_text(item)
        if not any(term.strip() and term.lower() in text for term in terms):
            return False
    return True


def evaluate_contraindications(patient_context: Dict[str, Any], items, rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """对处方项列表执行规则引擎，返回命中 finding 列表（warn/block 不做处置）。

    findings 元素：{rule_id, level, scope, item_id, item_name, message,
    status, source}；message 中的 {item_name} 占位替换为处方项名。
    """
    findings: List[Dict[str, Any]] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        for rule in rules or []:
            if not isinstance(rule, dict):
                continue
            if not _patient_matches(rule, patient_context):
                continue
            if not _item_matches(rule, item, patient_context):
                continue
            name = str(item.get("name") or "")
            findings.append({
                "rule_id": rule.get("rule_id"),
                "level": rule.get("level") or "warn",
                "scope": rule.get("scope") or "any",
                "item_id": item.get("item_id"),
                "item_name": name,
                "message": str(rule.get("message") or "").replace("{item_name}", name),
                "status": rule.get("status"),
                "source": rule.get("source"),
            })
    return findings


def split_findings(findings: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """按提示级别拆分：warnings 展示不阻断，blocks 在发布侧阻断。"""
    warnings = [finding for finding in findings or [] if finding.get("level") == "warn"]
    blocks = [finding for finding in findings or [] if finding.get("level") == "block"]
    return {"warnings": warnings, "blocks": blocks}


def findings_summary(findings: List[Dict[str, Any]], limit: int = 5) -> str:
    """把 findings 压成一段可放进错误消息/提示的文本（超出 limit 汇总条数）。"""
    rows = [str(finding.get("message") or finding.get("rule_id")) for finding in findings or []]
    if len(rows) > limit:
        return "；".join(rows[:limit]) + f"；其余 {len(rows) - limit} 条略"
    return "；".join(rows)
