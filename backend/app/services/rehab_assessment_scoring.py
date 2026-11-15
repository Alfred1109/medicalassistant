"""康复评估的评分口径与前后对比判定（W2-E 大文件拆分）。

从 `rehabilitation_service.py` 拆出的**纯计算**部分：量表换算、权重与
「变化是否算改进」的判定口径。这套口径按临床量表变更，不随存储与写入
路径变化，故独立成模块；评估的读写仍由 RehabilitationService 承担。

本模块只做计算，不访问数据库、不产生错误码。
"""
from typing import Any, Dict

# 参与总体评分的四个维度及其权重（合计 1.0）
SCORE_WEIGHTS = {
    "range_of_motion": 0.3,
    "muscle_strength": 0.3,
    "pain_level": 0.2,
    "functional_status": 0.2,
}

# 对比时逐项比对的评估维度
COMPARISON_CATEGORIES = ("range_of_motion", "muscle_strength", "pain_level",
                         "functional_status")


def calculate_assessment_scores(assessment: Dict[str, Any]) -> Dict[str, float]:
    """计算康复评估得分。"""
    scores = {}

    # 计算关节活动度得分 (range_of_motion)
    if "range_of_motion" in assessment:
        rom_values = [v for v in assessment["range_of_motion"].values() if isinstance(v, (int, float))]
        if rom_values:
            # 假设正常关节活动度为100，计算平均活动度恢复比例
            scores["range_of_motion"] = sum(rom_values) / len(rom_values)
        else:
            scores["range_of_motion"] = 0
    else:
        scores["range_of_motion"] = 0

    # 计算肌肉力量得分 (muscle_strength)
    if "muscle_strength" in assessment:
        # 假设肌肉力量使用0-5量表评分
        strength_values = [v for v in assessment["muscle_strength"].values() if isinstance(v, (int, float))]
        if strength_values:
            # 将0-5转换为0-100的百分比
            scores["muscle_strength"] = (sum(strength_values) / len(strength_values)) * 20  # 5分转为100分
        else:
            scores["muscle_strength"] = 0
    else:
        scores["muscle_strength"] = 0

    # 计算疼痛水平得分 (pain_level)
    if "pain_level" in assessment:
        # 假设疼痛使用0-10量表，0表示无痛，10表示剧痛
        pain_values = [v for v in assessment["pain_level"].values() if isinstance(v, (int, float))]
        if pain_values:
            # 反向计算得分，疼痛越低分数越高
            avg_pain = sum(pain_values) / len(pain_values)
            scores["pain_level"] = 100 - (avg_pain * 10)  # 0分痛反转为100分，10分痛反转为0分
        else:
            scores["pain_level"] = 100  # 无疼痛记录假设为满分
    else:
        scores["pain_level"] = 100

    # 计算功能状态得分 (functional_status)
    if "functional_status" in assessment:
        func_values = [v for v in assessment["functional_status"].values() if isinstance(v, (int, float))]
        if func_values:
            # 假设功能状态使用0-100评分
            scores["functional_status"] = sum(func_values) / len(func_values)
        else:
            scores["functional_status"] = 0
    else:
        scores["functional_status"] = 0

    # 计算总体评分，加权平均
    scores["overall"] = sum(score * SCORE_WEIGHTS[category]
                            for category, score in scores.items())

    return scores


def is_improvement(category: str, difference: float) -> bool:
    """判断变化是否为改进。"""
    # 对于疼痛，减少是改进；对于其他指标，增加是改进
    return (category == "pain_level" and difference < 0) or (category != "pain_level" and difference > 0)


def compare_assessments(current: Dict[str, Any], previous: Dict[str, Any]) -> Dict[str, Any]:
    """计算两次评估的逐项差异与总体评分差异。

    返回值即响应中的 `differences` 部分；数值型指标同时给出绝对差与百分比
    （上一次为 0 时百分比如实为 None），并按维度给出 improved/declined 判定。
    """
    differences = {}
    for category in COMPARISON_CATEGORIES:
        if category in current and category in previous:
            diff = {}
            for key in current[category]:
                if key in previous[category]:
                    curr_val = current[category][key]
                    prev_val = previous[category][key]

                    if isinstance(curr_val, (int, float)) and isinstance(prev_val, (int, float)):
                        absolute_diff = curr_val - prev_val
                        if prev_val != 0:
                            percent_diff = (absolute_diff / abs(prev_val)) * 100
                        else:
                            percent_diff = None

                        diff[key] = {
                            "absolute": absolute_diff,
                            "percent": percent_diff,
                            "trend": "improved" if is_improvement(category, absolute_diff) else "declined"
                        }
            differences[category] = diff

    # 计算总体评分差异
    if "scores" in current and "scores" in previous:
        score_diff = {
            "overall": current["scores"]["overall"] - previous["scores"]["overall"],
            "percent_change": ((current["scores"]["overall"] - previous["scores"]["overall"]) /
                              max(1, previous["scores"]["overall"])) * 100
        }
        differences["scores"] = score_diff

    return differences
