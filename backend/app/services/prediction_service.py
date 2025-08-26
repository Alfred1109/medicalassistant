from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
from bson.objectid import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler
import joblib
import os
import json

class PredictionService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.models_collection = db.prediction_models
        self.predictions_collection = db.rehab_predictions
        self.assessments_collection = db.rehab_assessments
        self.plans_collection = db.rehab_plans
        self.progress_collection = db.rehab_progress
        
    async def predict_rehab_outcome(
        self, 
        patient_id: str, 
        plan_id: str,
        prediction_days: int = 30,
        method: str = "ensemble"
    ) -> Dict[str, Any]:
        """
        预测康复效果
        
        Args:
            patient_id: 患者ID
            plan_id: 康复计划ID
            prediction_days: 预测未来天数
            method: 预测方法 (linear, ensemble)
            
        Returns:
            预测结果
        """
        try:
            # 获取患者的康复评估历史数据
            assessments = await self._get_patient_assessments(patient_id, plan_id)
            if not assessments or len(assessments) < 2:
                return {
                    "status": "error",
                    "message": "没有足够的历史评估数据进行预测(至少需要2条评估记录)",
                    "patient_id": patient_id,
                    "plan_id": plan_id
                }
            
            # 获取康复进度记录
            progress_data = await self._get_rehab_progress(plan_id)
            
            # 组织数据用于预测
            assessment_timestamps = []
            assessment_scores = {}
            assessment_categories = set()
            
            for assessment in assessments:
                date = assessment.get("assessment_date", assessment.get("created_at"))
                if isinstance(date, str):
                    date = datetime.fromisoformat(date.replace('Z', '+00:00'))
                
                assessment_timestamps.append(date)
                
                scores = assessment.get("scores", {})
                for category, score in scores.items():
                    assessment_categories.add(category)
                    if category not in assessment_scores:
                        assessment_scores[category] = []
                    assessment_scores[category].append(score)
            
            # 排序数据点（按时间）
            sorted_data = self._sort_assessment_data(assessment_timestamps, assessment_scores)
            
            # 根据方法进行预测
            predictions = {}
            confidence_intervals = {}
            
            for category in assessment_categories:
                if category in sorted_data and len(sorted_data[category]) >= 2:
                    # 基于方法选择预测模型
                    if method == "linear":
                        pred_values, conf_intervals = self._linear_prediction(
                            sorted_data["timestamps"], 
                            sorted_data[category],
                            prediction_days
                        )
                    elif method == "ensemble":
                        # 使用多个模型进行集成预测
                        pred_values, conf_intervals = self._ensemble_prediction(
                            sorted_data["timestamps"], 
                            sorted_data[category],
                            prediction_days
                        )
                    else:
                        # 默认使用线性预测
                        pred_values, conf_intervals = self._linear_prediction(
                            sorted_data["timestamps"], 
                            sorted_data[category],
                            prediction_days
                        )
                    
                    predictions[category] = pred_values
                    confidence_intervals[category] = conf_intervals
            
            # 保存预测结果
            prediction_id = await self._save_prediction_result(
                patient_id, 
                plan_id, 
                predictions, 
                confidence_intervals,
                method,
                sorted_data,
                prediction_days
            )
            
            # 构建响应
            last_assessment_date = sorted_data["timestamps"][-1]
            prediction_dates = [
                (last_assessment_date + timedelta(days=i)).strftime("%Y-%m-%d")
                for i in range(1, prediction_days + 1)
            ]
            
            result = {
                "status": "success",
                "prediction_id": prediction_id,
                "patient_id": patient_id,
                "plan_id": plan_id,
                "method": method,
                "historical_data": {
                    "dates": [d.strftime("%Y-%m-%d") for d in sorted_data["timestamps"]],
                    "values": {category: values for category, values in sorted_data.items() if category != "timestamps"}
                },
                "prediction": {
                    "dates": prediction_dates,
                    "values": predictions,
                    "confidence_intervals": confidence_intervals
                },
                "interpretation": self._generate_prediction_interpretation(predictions, confidence_intervals),
                "created_at": datetime.utcnow().isoformat()
            }
            
            return result
            
        except Exception as e:
            print(f"预测康复效果出错: {str(e)}")
            return {
                "status": "error",
                "message": f"预测过程中发生错误: {str(e)}",
                "patient_id": patient_id,
                "plan_id": plan_id
            }
    
    async def get_prediction_by_id(self, prediction_id: str) -> Optional[Dict[str, Any]]:
        """获取预测结果详情"""
        try:
            prediction = await self.predictions_collection.find_one({"_id": ObjectId(prediction_id)})
            if prediction:
                prediction["_id"] = str(prediction["_id"])
                return prediction
        except Exception as e:
            print(f"获取预测结果失败: {str(e)}")
        return None
    
    async def list_patient_predictions(self, patient_id: str, plan_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取患者的所有预测结果"""
        try:
            filter_dict = {"patient_id": patient_id}
            if plan_id:
                filter_dict["plan_id"] = plan_id
                
            cursor = self.predictions_collection.find(filter_dict).sort("created_at", -1)
            predictions = []
            
            async for prediction in cursor:
                prediction["_id"] = str(prediction["_id"])
                predictions.append(prediction)
                
            return predictions
        except Exception as e:
            print(f"获取患者预测列表失败: {str(e)}")
            return []
            
    async def compare_predicted_vs_actual(
        self, 
        prediction_id: str, 
        assessment_id: str
    ) -> Dict[str, Any]:
        """比较预测结果和实际评估结果"""
        try:
            # 获取预测
            prediction = await self.get_prediction_by_id(prediction_id)
            if not prediction:
                return {"status": "error", "message": "预测结果不存在"}
                
            # 获取评估
            try:
                assessment = await self.assessments_collection.find_one({"_id": ObjectId(assessment_id)})
                if not assessment:
                    return {"status": "error", "message": "评估结果不存在"}
                assessment["_id"] = str(assessment["_id"])
            except Exception:
                return {"status": "error", "message": "获取评估结果失败"}
                
            # 获取评估日期
            assessment_date = assessment.get("assessment_date", assessment.get("created_at"))
            if isinstance(assessment_date, str):
                assessment_date = datetime.fromisoformat(assessment_date.replace('Z', '+00:00'))
            
            # 获取预测中的日期
            prediction_dates = prediction.get("prediction", {}).get("dates", [])
            prediction_values = prediction.get("prediction", {}).get("values", {})
            
            # 查找最接近的预测日期
            closest_date_index = None
            min_days_diff = float('inf')
            
            for i, date_str in enumerate(prediction_dates):
                pred_date = datetime.strptime(date_str, "%Y-%m-%d")
                days_diff = abs((assessment_date - pred_date).days)
                if days_diff < min_days_diff:
                    min_days_diff = days_diff
                    closest_date_index = i
            
            if closest_date_index is None:
                return {
                    "status": "error", 
                    "message": "无法找到与评估日期匹配的预测数据点"
                }
                
            # 比较结果
            comparison = {
                "status": "success",
                "prediction_id": prediction_id,
                "assessment_id": assessment_id,
                "assessment_date": assessment_date.strftime("%Y-%m-%d"),
                "prediction_date": prediction_dates[closest_date_index],
                "days_difference": min_days_diff,
                "categories": {},
                "overall_accuracy": 0.0
            }
            
            # 计算每个类别的差异
            actual_scores = assessment.get("scores", {})
            category_accuracy = []
            
            for category, actual_score in actual_scores.items():
                if category in prediction_values:
                    predicted_score = prediction_values[category][closest_date_index]
                    difference = actual_score - predicted_score
                    percent_diff = (difference / predicted_score) * 100 if predicted_score != 0 else 0
                    accuracy = max(0, 100 - abs(percent_diff))
                    
                    comparison["categories"][category] = {
                        "predicted": predicted_score,
                        "actual": actual_score,
                        "difference": difference,
                        "accuracy_percent": accuracy 
                    }
                    
                    category_accuracy.append(accuracy)
            
            # 计算整体准确度
            if category_accuracy:
                comparison["overall_accuracy"] = sum(category_accuracy) / len(category_accuracy)
                
            # 更新预测记录中的准确度数据
            await self.predictions_collection.update_one(
                {"_id": ObjectId(prediction_id)},
                {"$set": {
                    "accuracy_data": {
                        "assessment_id": assessment_id,
                        "comparison": comparison
                    },
                    "updated_at": datetime.utcnow()
                }}
            )
                
            return comparison
            
        except Exception as e:
            print(f"比较预测与实际结果出错: {str(e)}")
            return {
                "status": "error",
                "message": f"比较过程中发生错误: {str(e)}"
            }
    
    def _linear_prediction(
        self, 
        timestamps: List[datetime], 
        values: List[float],
        prediction_days: int
    ) -> Tuple[List[float], List[Dict[str, float]]]:
        """使用简单线性回归进行预测"""
        # 转换时间戳为数值特征（距离起始日的天数）
        start_date = min(timestamps)
        X = np.array([(date - start_date).days for date in timestamps]).reshape(-1, 1)
        y = np.array(values)
        
        # 拟合线性模型
        model = LinearRegression()
        model.fit(X, y)
        
        # 生成预测日期
        X_pred = np.array(range(X[-1][0] + 1, X[-1][0] + prediction_days + 1)).reshape(-1, 1)
        
        # 预测值
        y_pred = model.predict(X_pred)
        
        # 计算置信区间（基于简单误差估计）
        y_train_pred = model.predict(X)
        residuals = y - y_train_pred
        residual_std = np.std(residuals)
        
        # 95%置信区间（约为2倍标准差）
        confidence_intervals = []
        for pred in y_pred:
            confidence_intervals.append({
                "lower": pred - 2 * residual_std,
                "upper": pred + 2 * residual_std
            })
        
        return y_pred.tolist(), confidence_intervals
    
    def _ensemble_prediction(
        self, 
        timestamps: List[datetime], 
        values: List[float],
        prediction_days: int
    ) -> Tuple[List[float], List[Dict[str, float]]]:
        """使用多模型集成进行预测"""
        # 当前仅实现线性模型，未来可以添加更多算法
        # TODO: 添加ARIMA、随机森林等模型
        return self._linear_prediction(timestamps, values, prediction_days)
    
    def _sort_assessment_data(
        self,
        timestamps: List[datetime],
        scores: Dict[str, List[float]]
    ) -> Dict[str, Any]:
        """排序评估数据（按时间顺序）"""
        # 将时间戳和评分数据组合
        data_points = []
        for i, timestamp in enumerate(timestamps):
            point = {"timestamp": timestamp}
            for category, values in scores.items():
                if i < len(values):
                    point[category] = values[i]
            data_points.append(point)
        
        # 按时间戳排序
        data_points.sort(key=lambda x: x["timestamp"])
        
        # 重新组织数据
        sorted_data = {"timestamps": []}
        for category in scores.keys():
            sorted_data[category] = []
            
        for point in data_points:
            sorted_data["timestamps"].append(point["timestamp"])
            for category in scores.keys():
                if category in point:
                    sorted_data[category].append(point[category])
                    
        return sorted_data
        
    async def _get_patient_assessments(
        self, 
        patient_id: str, 
        plan_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """获取患者的康复评估历史"""
        filter_dict = {"patient_id": patient_id}
        if plan_id:
            filter_dict["plan_id"] = plan_id
            
        cursor = self.assessments_collection.find(filter_dict).sort("assessment_date", 1)
        assessments = []
        
        async for assessment in cursor:
            assessment["_id"] = str(assessment["_id"])
            assessments.append(assessment)
            
        return assessments
        
    async def _get_rehab_progress(self, plan_id: str) -> List[Dict[str, Any]]:
        """获取康复计划的进度记录"""
        cursor = self.progress_collection.find({"plan_id": plan_id}).sort("recorded_at", 1)
        progress = []
        
        async for record in cursor:
            record["_id"] = str(record["_id"])
            progress.append(record)
            
        return progress
        
    async def _save_prediction_result(
        self,
        patient_id: str,
        plan_id: str,
        predictions: Dict[str, List[float]],
        confidence_intervals: Dict[str, List[Dict[str, float]]],
        method: str,
        historical_data: Dict[str, Any],
        prediction_days: int
    ) -> str:
        """保存预测结果到数据库"""
        # 获取计划信息
        plan = None
        try:
            plan_doc = await self.plans_collection.find_one({"_id": ObjectId(plan_id)})
            if plan_doc:
                plan = {
                    "_id": str(plan_doc["_id"]),
                    "name": plan_doc.get("name", ""),
                    "patient_name": plan_doc.get("patient_name", ""),
                    "condition": plan_doc.get("condition", "")
                }
        except Exception:
            pass
            
        # 创建预测记录
        prediction_record = {
            "patient_id": patient_id,
            "plan_id": plan_id,
            "plan_info": plan,
            "method": method,
            "prediction_days": prediction_days,
            "historical_data": {
                "dates": [d.strftime("%Y-%m-%d") for d in historical_data["timestamps"]],
                "values": {k: v for k, v in historical_data.items() if k != "timestamps"}
            },
            "prediction": {
                "dates": [
                    (historical_data["timestamps"][-1] + timedelta(days=i)).strftime("%Y-%m-%d")
                    for i in range(1, prediction_days + 1)
                ],
                "values": predictions,
                "confidence_intervals": confidence_intervals
            },
            "created_at": datetime.utcnow(),
            "status": "active"
        }
        
        result = await self.predictions_collection.insert_one(prediction_record)
        return str(result.inserted_id)
        
    def _generate_prediction_interpretation(
        self,
        predictions: Dict[str, List[float]],
        confidence_intervals: Dict[str, List[Dict[str, float]]]
    ) -> Dict[str, str]:
        """生成预测结果的解释文本"""
        interpretations = {}
        
        for category, values in predictions.items():
            # 简单趋势判断
            if len(values) >= 2:
                start_value = values[0]
                end_value = values[-1]
                change = end_value - start_value
                percent_change = (change / start_value) * 100 if start_value != 0 else 0
                
                if abs(percent_change) < 5:
                    trend = "基本保持稳定"
                else:
                    direction = "上升" if change > 0 else "下降"
                    magnitude = "显著" if abs(percent_change) > 20 else "轻微"
                    trend = f"{magnitude}{direction}"
                
                # 置信区间宽度
                if category in confidence_intervals and confidence_intervals[category]:
                    first_ci = confidence_intervals[category][0]
                    last_ci = confidence_intervals[category][-1]
                    
                    first_width = first_ci["upper"] - first_ci["lower"]
                    last_width = last_ci["upper"] - last_ci["lower"]
                    
                    confidence_trend = ""
                    if last_width > first_width * 1.5:
                        confidence_trend = "，但预测不确定性随时间增加"
                    elif last_width < first_width * 0.8:
                        confidence_trend = "，预测确定性较高"
                    
                    interpretations[category] = f"预计将{trend}{confidence_trend}。从{start_value:.1f}变化到{end_value:.1f}，变化幅度约{abs(percent_change):.1f}%。"
                else:
                    interpretations[category] = f"预计将{trend}。从{start_value:.1f}变化到{end_value:.1f}，变化幅度约{abs(percent_change):.1f}%。"
            else:
                interpretations[category] = "数据点不足，无法生成可靠预测解释。"
                
        return interpretations 