"""CSV 导出转义：公式注入防护在两个导出器上是同一套规则。"""

import unittest

from app.clinical import workspace
from app.core.csv_export import csv_cell, csv_safe, csv_text


class CsvSafeTests(unittest.TestCase):
    def test_formula_prefixes_are_escaped(self):
        for value in ("=CMD()", "+1", "-1", "@SUM(1)", "  =1", "\tvalue", "\rvalue", "\nvalue"):
            self.assertTrue(csv_safe(value).startswith("'"), value)
        self.assertEqual(csv_safe("普通文字"), "普通文字")
        self.assertEqual(csv_safe(None), "")

    def test_numbers_keep_their_value(self):
        # 数值列加撇号会被表格软件读成文本，数据保真要求不加
        self.assertEqual(csv_safe(-5), "-5")
        self.assertEqual(csv_safe(140), "140")
        self.assertEqual(csv_safe(0.5), "0.5")

    def test_quoting_is_unchanged_for_separators(self):
        self.assertEqual(csv_cell("a,b"), '"a,b"')
        self.assertEqual(csv_cell('a"b'), '"a""b"')
        self.assertEqual(csv_cell("plain"), "plain")


class IndicatorsCsvTests(unittest.TestCase):
    def test_indicator_value_cannot_carry_a_formula(self):
        result = {
            "message": "对照说明",
            "indicators": [{
                "label": "血压", "source_label": "手工记录", "value": "=1+1",
                "unit": "mmHg", "low": 90, "high": 140, "icf_code": "b455",
                "state": "outside",
            }],
        }
        text = workspace.indicators_csv(result)
        self.assertIn("'=1+1", text)
        self.assertNotIn(",=1+1,", text)

    def test_numeric_bounds_stay_numeric(self):
        result = {
            "message": "对照说明",
            "indicators": [{
                "label": "血压", "source_label": "手工记录", "value": 128,
                "unit": "mmHg", "low": 90, "high": 140, "icf_code": "b455",
                "state": "inside",
            }],
        }
        text = workspace.indicators_csv(result)
        self.assertIn(",128,mmHg,90,140,", text)


class CsvTextTests(unittest.TestCase):
    def test_rows_are_escaped_and_newline_separated(self):
        text = csv_text([["a", "=b"], ["c,d", "e"]])
        self.assertEqual(text, "a,'=b\n\"c,d\",e\n")


if __name__ == "__main__":
    unittest.main()
