"""T72 禁忌规则引擎与临床口径配置的纯函数契约测试（不触库，恒跑）。"""
import unittest
from types import SimpleNamespace

from pydantic import ValidationError

from app.core.exceptions import AppBaseException
from app.schemas.rehab_publication import PublicationItem, PublishDraft
from app.services.rehab_clinical_config import (
    CLINICAL_REVIEW_STATUS, DEFAULT_SIGNATURE_DECLARATION, RULES_COLLECTION,
    SAMPLE_RULES, SIGNATURE_COLLECTION, load_contraindication_rules,
    load_signature_declaration, normalize_rule,
)
from app.services.rehab_contraindication_service import (
    build_patient_context, evaluate_contraindications, findings_summary,
    item_search_text, split_findings,
)


def sample_rules():
    return [dict(rule) for rule in SAMPLE_RULES]


class PublicationSchemaIncrementTests(unittest.TestCase):
    def test_course_and_execution_requirements_are_incremental_optional_fields(self):
        item = PublicationItem(intervention_type="exercise", name="股四头肌训练",
                               course={"duration_days": 14, "sessions_total": 6, "note": "两周复评"},
                               execution_requirements=["每周复评一次", " 疼痛加重即停 "])
        self.assertEqual(item.course.duration_days, 14)
        self.assertEqual(item.execution_requirements, ["每周复评一次", "疼痛加重即停"])
        # 历史快照形态（无增量字段）仍然可投影
        legacy = PublicationItem(intervention_type="exercise", name="历史项")
        self.assertIsNone(legacy.course)
        self.assertIsNone(legacy.execution_requirements)

    def test_course_and_requirements_reject_invalid_values(self):
        for course in ({"duration_days": 0}, {"sessions_total": -1}, {}, {"extra": 1}):
            with self.assertRaises(ValidationError):
                PublicationItem(intervention_type="exercise", name="x", course=course)
        with self.assertRaises(ValidationError):
            PublicationItem(intervention_type="exercise", name="x", execution_requirements=[""])
        with self.assertRaises(ValidationError):
            PublicationItem(intervention_type="exercise", name="x", execution_requirements=["x" * 501])
        with self.assertRaises(ValidationError):
            PublicationItem(intervention_type="exercise", name="x", execution_requirements=[])

    def test_declaration_acknowledged_is_optional_but_true_when_supplied(self):
        base = {"request_id": "request-one", "draft_id": str(ObjectIdLiteral()),
                "expected_draft_revision": 0, "confirmed": True, "confirmation_note": "checked"}
        self.assertIsNone(PublishDraft(**base).declaration_acknowledged)
        self.assertIs(True, PublishDraft(**{**base, "declaration_acknowledged": True}).declaration_acknowledged)
        with self.assertRaises(ValidationError):
            PublishDraft(**{**base, "declaration_acknowledged": False})


def ObjectIdLiteral():
    from bson import ObjectId
    return ObjectId()


class PatientContextTests(unittest.TestCase):
    def test_legacy_document_fields_are_projected(self):
        context = build_patient_context({
            "medical_info": {"diagnosis": "高血压，2型糖尿病"},
            "allergies": ["青霉素过敏", "磺胺"],
            "age": 72, "gender": "female",
        })
        self.assertIn("高血压", context["diagnoses"])
        self.assertIn("2型糖尿病", context["diagnoses"])
        self.assertEqual(context["allergies"], ["青霉素过敏", "磺胺"])
        self.assertEqual(context["age"], 72)
        self.assertEqual(context["gender"], "female")

    def test_canonical_document_fields_are_projected(self):
        context = build_patient_context({
            "medical_info": {"condition": "脑卒中"},
            "demographic_info": {"age": "65", "gender": "male"},
            "diagnosis": "高血压",
        })
        self.assertIn("脑卒中", context["diagnoses"])
        self.assertIn("高血压", context["diagnoses"])
        # 非数字年龄如实留空，不推断
        self.assertIsNone(context["age"])
        self.assertEqual(context["gender"], "male")

    def test_missing_or_malformed_documents_stay_empty(self):
        self.assertEqual(build_patient_context({})["allergies"], [])
        self.assertEqual(build_patient_context(None)["diagnoses"], [])
        self.assertEqual(build_patient_context({"medical_info": "broken"})["diagnoses"], [])


class ItemSearchTextTests(unittest.TestCase):
    def test_searchable_text_covers_prescription_fields(self):
        text = item_search_text({
            "name": "抗感染用药", "description": None,
            "medication_fields": {"drug_ref": "青霉素V钾片"},
            "diet_fields": {"food_restrictions": ["海鲜"]},
            "course": {"note": "两周疗程"},
            "execution_requirements": ["饭后服用"],
            "contraindications": ["肝功能不全"],
        })
        for term in ("青霉素v钾片", "海鲜", "两周疗程", "饭后服用", "肝功能不全", "抗感染用药"):
            self.assertIn(term, text)


class RuleEngineTests(unittest.TestCase):
    def medication(self, name="青霉素V钾片", **extra):
        return {"item_id": "a" * 24, "intervention_type": "medication", "name": name,
                "medication_fields": {"drug_ref": name}, **extra}

    def test_block_rule_fires_on_allergen_cross_match(self):
        context = build_patient_context({"allergies": ["青霉素过敏"]})
        findings = evaluate_contraindications(context, [self.medication()], sample_rules())
        self.assertEqual([finding["rule_id"] for finding in findings],
                         ["sample-block-penicillin-allergy"])
        finding = findings[0]
        self.assertEqual(finding["level"], "block")
        self.assertEqual(finding["status"], CLINICAL_REVIEW_STATUS)
        self.assertIn("青霉素V钾片", finding["message"])
        self.assertEqual(finding["item_id"], "a" * 24)

    def test_rules_miss_without_patient_hit(self):
        context = build_patient_context({"allergies": ["花粉"], "medical_info": {"diagnosis": "骨折"}})
        self.assertEqual(evaluate_contraindications(context, [self.medication()], sample_rules()), [])
        # 患者无过敏记录时交叉匹配规则不命中（不拿空过敏史猜规则）
        self.assertEqual(evaluate_contraindications(build_patient_context({}), [self.medication()], sample_rules()), [])

    def test_warn_rule_requires_diagnosis_and_item_text(self):
        context = build_patient_context({"medical_info": {"diagnosis": "高血压"}})
        hit = evaluate_contraindications(context, [{"intervention_type": "exercise", "name": "倒立拉伸"}], sample_rules())
        self.assertEqual([finding["rule_id"] for finding in hit], ["sample-warn-hypertension-inversion"])
        miss = evaluate_contraindications(context, [{"intervention_type": "exercise", "name": "平地步行"}], sample_rules())
        self.assertEqual(miss, [])
        # scope 过滤：饮食项不触发运动规则
        wrong_scope = evaluate_contraindications(context, [{"intervention_type": "diet", "name": "倒立食谱"}], sample_rules())
        self.assertEqual(wrong_scope, [])

    def test_age_rule_skips_unknown_age(self):
        context = build_patient_context({"age": 75, "medical_info": {"diagnosis": "骨关节炎"}})
        hit = evaluate_contraindications(context, [{"intervention_type": "exercise", "name": "大强度负重训练"}], sample_rules())
        self.assertEqual([finding["rule_id"] for finding in hit], ["sample-warn-elderly-high-load"])
        unknown = evaluate_contraindications({"age": None, "diagnoses": [], "diagnosis_text": "", "allergies": []},
                                             [{"intervention_type": "exercise", "name": "大强度负重训练"}], sample_rules())
        self.assertEqual(unknown, [])

    def test_custom_collection_rules_drive_the_engine(self):
        rules = [normalize_rule({
            "rule_id": "custom-block", "level": "block", "scope": "any",
            "description": "自定义阻断", "message": "自定义规则命中：{item_name}",
            "when_item": {"text_includes_any": ["特殊禁用"]},
        }, "collection")]
        findings = evaluate_contraindications(build_patient_context({}),
                                              [{"intervention_type": "exercise", "name": "特殊禁用动作"}], rules)
        self.assertEqual([finding["rule_id"] for finding in findings], ["custom-block"])
        self.assertEqual(findings[0]["source"], "collection")

    def test_split_and_summary(self):
        findings = [{"level": "warn", "message": "w1"}, {"level": "block", "message": "b1"},
                    {"level": "block", "message": "b2"}]
        split = split_findings(findings)
        self.assertEqual([row["message"] for row in split["warnings"]], ["w1"])
        self.assertEqual([row["message"] for row in split["blocks"]], ["b1", "b2"])
        self.assertEqual(findings_summary(split["blocks"]), "b1；b2")
        many = [{"level": "block", "message": f"m{index}"} for index in range(7)]
        self.assertIn("其余 2 条略", findings_summary(many, limit=5))


class ConfigContractTests(unittest.TestCase):
    def test_builtin_samples_are_marked_for_clinical_review(self):
        identifiers = set()
        for rule in SAMPLE_RULES:
            identifiers.add(rule["rule_id"])
            self.assertEqual(rule["status"], CLINICAL_REVIEW_STATUS)
            self.assertIn(rule["level"], ("warn", "block"))
            self.assertEqual(rule["source"], "builtin-sample")
            self.assertIn("{item_name}", rule["message"])
        self.assertEqual(len(identifiers), len(SAMPLE_RULES))

    def test_default_signature_declaration_is_marked_for_clinical_review(self):
        self.assertEqual(DEFAULT_SIGNATURE_DECLARATION["status"], CLINICAL_REVIEW_STATUS)
        self.assertTrue(DEFAULT_SIGNATURE_DECLARATION["declaration"].strip())

    def test_normalize_rule_rejects_structurally_broken_rules(self):
        base = {"rule_id": "r1", "level": "warn", "description": "d", "message": "命中：{item_name}",
                "when_item": {"text_includes_any": ["x"]}}
        self.assertEqual(normalize_rule(base, "collection")["rule_id"], "r1")
        for broken in ({}, {**base, "level": "fatal"}, {**base, "message": "没有占位"},
                       {**base, "when_item": {"text_includes_any": []}},
                       {**base, "when_patient": {"age_above": -1}},
                       {**base, "when_item": {"intervention_types": ["massage"]}},
                       {"rule_id": "r2", "level": "warn", "description": "d", "message": "{item_name}"}):
            with self.assertRaises(ValueError):
                normalize_rule(broken, "collection")

    def test_normalize_rule_defaults_status_to_clinical_review(self):
        rule = normalize_rule({"rule_id": "r2", "level": "block", "description": "d",
                               "message": "{item_name}", "when_item": {"text_includes_any": ["x"]}},
                              "collection")
        self.assertEqual(rule["status"], CLINICAL_REVIEW_STATUS)
        self.assertTrue(rule["allergen_cross_match"] is False)


class FakeAsyncCollection:
    def __init__(self, docs=None, error=None):
        self.docs = docs or []
        self.error = error

    def find(self, query):
        if self.error:
            raise self.error
        return self

    async def to_list(self, length):
        if self.error:
            raise self.error
        return self.docs

    async def find_one(self, query):
        if self.error:
            raise self.error
        return self.docs[0] if self.docs else None


class FakeDatabase(SimpleNamespace):
    def __getitem__(self, name):
        return self.collections[name]


class ConfigLoaderTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_collection_falls_back_to_builtin_samples(self):
        db = FakeDatabase(collections={RULES_COLLECTION: FakeAsyncCollection([])})
        rules = await load_contraindication_rules(db)
        self.assertEqual([rule["rule_id"] for rule in rules],
                         [rule["rule_id"] for rule in SAMPLE_RULES])
        signature = await load_signature_declaration(FakeDatabase(collections={SIGNATURE_COLLECTION: FakeAsyncCollection([])}))
        self.assertEqual(signature, DEFAULT_SIGNATURE_DECLARATION)

    async def test_collection_rules_replace_builtin_samples_whole_set(self):
        docs = [{"rule_id": "custom-only", "level": "warn", "description": "d",
                 "message": "命中 {item_name}", "when_item": {"text_includes_any": ["x"]}}]
        db = FakeDatabase(collections={RULES_COLLECTION: FakeAsyncCollection(docs)})
        rules = await load_contraindication_rules(db)
        self.assertEqual([rule["rule_id"] for rule in rules], ["custom-only"])
        self.assertEqual(rules[0]["source"], "collection")

    async def test_unreadable_or_invalid_rule_sets_fail_closed(self):
        db = FakeDatabase(collections={RULES_COLLECTION: FakeAsyncCollection(error=RuntimeError("down"))})
        with self.assertRaises(AppBaseException) as caught:
            await load_contraindication_rules(db)
        self.assertEqual(caught.exception.error_code, "REHAB_CLINICAL_RULES_UNAVAILABLE")
        broken = FakeDatabase(collections={RULES_COLLECTION: FakeAsyncCollection([{"rule_id": "bad"}])})
        with self.assertRaises(AppBaseException) as invalid:
            await load_contraindication_rules(broken)
        self.assertEqual(invalid.exception.error_code, "REHAB_CLINICAL_RULES_INVALID")

    async def test_signature_declaration_override_and_fail_closed(self):
        override = FakeDatabase(collections={SIGNATURE_COLLECTION: FakeAsyncCollection(
            [{"key": "publish_signature", "declaration": " 临床确认后的声明 ", "status": "confirmed"}])})
        signature = await load_signature_declaration(override)
        self.assertEqual(signature["declaration"], "临床确认后的声明")
        self.assertEqual(signature["source"], "collection")
        missing = FakeDatabase(collections={SIGNATURE_COLLECTION: FakeAsyncCollection(
            [{"key": "publish_signature", "declaration": "  "}], )})
        with self.assertRaises(AppBaseException) as caught:
            await load_signature_declaration(missing)
        self.assertEqual(caught.exception.error_code, "REHAB_CLINICAL_SIGNATURE_INVALID")
        down = FakeDatabase(collections={SIGNATURE_COLLECTION: FakeAsyncCollection(error=RuntimeError("down"))})
        with self.assertRaises(AppBaseException) as unreadable:
            await load_signature_declaration(down)
        self.assertEqual(unreadable.exception.error_code, "REHAB_CLINICAL_SIGNATURE_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
