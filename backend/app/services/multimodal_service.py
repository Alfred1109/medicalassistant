from typing import Dict, List, Any, Optional, Union
from datetime import datetime, timedelta
import numpy as np
from bson.objectid import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
import json
import os

class MultimodalAnalysisService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.analysis_collection = db.multimodal_analysis
        self.device_data_collection = db.device_data
        self.assessments_collection = db.rehab_assessments
        self.exercise_logs_collection = db.exercise_logs
        self.health_records_collection = db.health_records
        
    async def analyze_multimodal_data(
        self, 
        patient_id: str,
        analysis_type: str = "comprehensive",
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        data_sources: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        执行多模态数据分析
        
        Args:
            patient_id: 患者ID
            analysis_type: 分析类型 (comprehensive, correlation, trend, pattern)
            start_date: 开始日期
            end_date: 结束日期
            data_sources: 数据源列表 (devices, assessments, exercises, health_records)
            
        Returns:
            分析结果
        """
        try:
            # 设置默认日期范围（如果未指定）
            if not end_date:
                end_date = datetime.utcnow()
            if not start_date:
                start_date = end_date - timedelta(days=90)  # 默认90天
                
            # 设置默认数据源（如果未指定）
            if not data_sources:
                data_sources = ["devices", "assessments", "exercises", "health_records"]
                
            # 收集各个来源的数据
            data_collection = {}
            
            # 收集设备数据
            if "devices" in data_sources:
                device_data = await self._get_device_data(patient_id, start_date, end_date)
                data_collection["devices"] = device_data
                
            # 收集评估数据
            if "assessments" in data_sources:
                assessment_data = await self._get_assessment_data(patient_id, start_date, end_date)
                data_collection["assessments"] = assessment_data
                
            # 收集运动记录
            if "exercises" in data_sources:
                exercise_data = await self._get_exercise_data(patient_id, start_date, end_date)
                data_collection["exercises"] = exercise_data
                
            # 收集健康记录
            if "health_records" in data_sources:
                health_data = await self._get_health_records(patient_id, start_date, end_date)
                data_collection["health_records"] = health_data
                
            # 检查是否有足够的数据进行分析
            if self._check_data_sufficiency(data_collection) is False:
                return {
                    "status": "error",
                    "message": "没有足够的数据进行多模态分析",
                    "patient_id": patient_id
                }
                
            # 根据分析类型执行不同的分析
            analysis_result = {}
            
            if analysis_type == "comprehensive" or analysis_type == "all":
                # 综合分析包含多种分析类型
                correlation_result = self._perform_correlation_analysis(data_collection)
                trend_result = self._perform_trend_analysis(data_collection)
                pattern_result = self._perform_pattern_analysis(data_collection)
                
                analysis_result = {
                    "correlation": correlation_result,
                    "trend": trend_result,
                    "pattern": pattern_result
                }
            elif analysis_type == "correlation":
                analysis_result = self._perform_correlation_analysis(data_collection)
            elif analysis_type == "trend":
                analysis_result = self._perform_trend_analysis(data_collection)
            elif analysis_type == "pattern":
                analysis_result = self._perform_pattern_analysis(data_collection)
            else:
                return {
                    "status": "error",
                    "message": f"不支持的分析类型: {analysis_type}",
                    "patient_id": patient_id
                }
                
            # 生成分析摘要
            summary = self._generate_analysis_summary(analysis_result, analysis_type)
            
            # 保存分析结果
            analysis_id = await self._save_analysis_result(
                patient_id,
                analysis_type,
                data_sources,
                analysis_result,
                summary,
                start_date,
                end_date
            )
            
            # 构建响应
            result = {
                "status": "success",
                "analysis_id": analysis_id,
                "patient_id": patient_id,
                "analysis_type": analysis_type,
                "period": {
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat()
                },
                "data_sources": data_sources,
                "summary": summary,
                "results": analysis_result,
                "created_at": datetime.utcnow().isoformat()
            }
            
            return result
            
        except Exception as e:
            print(f"多模态数据分析出错: {str(e)}")
            return {
                "status": "error",
                "message": f"分析过程中发生错误: {str(e)}",
                "patient_id": patient_id
            }
    
    async def get_analysis_by_id(self, analysis_id: str) -> Optional[Dict[str, Any]]:
        """获取分析结果详情"""
        try:
            analysis = await self.analysis_collection.find_one({"_id": ObjectId(analysis_id)})
            if analysis:
                analysis["_id"] = str(analysis["_id"])
                return analysis
        except Exception as e:
            print(f"获取分析结果失败: {str(e)}")
        return None
    
    async def list_patient_analyses(
        self, 
        patient_id: str,
        analysis_type: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """获取患者的分析历史"""
        try:
            filter_dict = {"patient_id": patient_id}
            if analysis_type:
                filter_dict["analysis_type"] = analysis_type
                
            cursor = self.analysis_collection.find(filter_dict).sort("created_at", -1).limit(limit)
            analyses = []
            
            async for analysis in cursor:
                analysis["_id"] = str(analysis["_id"])
                analyses.append(analysis)
                
            return analyses
        except Exception as e:
            print(f"获取患者分析列表失败: {str(e)}")
            return []
    
    async def integrate_medical_records(
        self,
        patient_id: str,
        analysis_id: str,
        medical_records: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """整合医疗记录到现有分析中"""
        try:
            # 获取现有分析
            analysis = await self.get_analysis_by_id(analysis_id)
            if not analysis:
                return {"status": "error", "message": "分析结果不存在"}
                
            # 更新分析结果，添加医疗记录信息
            updated_analysis = analysis.copy()
            if "medical_records" not in updated_analysis:
                updated_analysis["medical_records"] = []
                
            updated_analysis["medical_records"].extend(medical_records)
            updated_analysis["updated_at"] = datetime.utcnow()
            
            # 重新生成分析摘要
            if "results" in updated_analysis:
                # 在这里可以基于新添加的医疗记录执行额外分析
                # 为简化起见，我们只更新摘要信息
                summary = self._generate_analysis_summary(
                    updated_analysis["results"],
                    updated_analysis["analysis_type"],
                    medical_records
                )
                updated_analysis["summary"] = summary
            
            # 更新数据库
            result = await self.analysis_collection.update_one(
                {"_id": ObjectId(analysis_id)},
                {"$set": updated_analysis}
            )
            
            if result.modified_count:
                return {
                    "status": "success",
                    "message": "医疗记录已成功整合到分析中",
                    "analysis_id": analysis_id
                }
            else:
                return {"status": "error", "message": "更新分析失败"}
                
        except Exception as e:
            print(f"整合医疗记录失败: {str(e)}")
            return {
                "status": "error",
                "message": f"整合过程中发生错误: {str(e)}"
            }
            
    async def _get_device_data(
        self, 
        patient_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict[str, Any]]:
        """获取设备数据"""
        filter_dict = {
            "patient_id": patient_id,
            "timestamp": {
                "$gte": start_date,
                "$lte": end_date
            }
        }
        
        cursor = self.device_data_collection.find(filter_dict).sort("timestamp", 1)
        data = []
        
        async for record in cursor:
            record["_id"] = str(record["_id"])
            data.append(record)
            
        return data
        
    async def _get_assessment_data(
        self, 
        patient_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict[str, Any]]:
        """获取评估数据"""
        filter_dict = {
            "patient_id": patient_id,
            "assessment_date": {
                "$gte": start_date,
                "$lte": end_date
            }
        }
        
        cursor = self.assessments_collection.find(filter_dict).sort("assessment_date", 1)
        data = []
        
        async for record in cursor:
            record["_id"] = str(record["_id"])
            data.append(record)
            
        return data
        
    async def _get_exercise_data(
        self, 
        patient_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict[str, Any]]:
        """获取运动记录"""
        filter_dict = {
            "patient_id": patient_id,
            "recorded_at": {
                "$gte": start_date,
                "$lte": end_date
            }
        }
        
        cursor = self.exercise_logs_collection.find(filter_dict).sort("recorded_at", 1)
        data = []
        
        async for record in cursor:
            record["_id"] = str(record["_id"])
            data.append(record)
            
        return data
        
    async def _get_health_records(
        self, 
        patient_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict[str, Any]]:
        """获取健康记录"""
        filter_dict = {
            "patient_id": patient_id,
            "record_date": {
                "$gte": start_date,
                "$lte": end_date
            }
        }
        
        cursor = self.health_records_collection.find(filter_dict).sort("record_date", 1)
        data = []
        
        async for record in cursor:
            record["_id"] = str(record["_id"])
            data.append(record)
            
        return data
    
    def _check_data_sufficiency(self, data_collection: Dict[str, List[Dict[str, Any]]]) -> bool:
        """检查是否有足够的数据进行分析"""
        # 至少需要两个数据源，且每个数据源至少有一条记录
        if len(data_collection) < 2:
            return False
            
        # 检查每个数据源是否有足够的数据
        has_sufficient_data = False
        data_source_count = 0
        
        for source, data in data_collection.items():
            if data and len(data) > 0:
                data_source_count += 1
                
        # 至少需要两个有数据的数据源
        has_sufficient_data = data_source_count >= 2
            
        return has_sufficient_data
    
    def _perform_correlation_analysis(self, data_collection: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
        """执行相关性分析"""
        # 这里是相关性分析的简化实现
        # 在实际项目中，可以使用更复杂的算法和统计方法
        
        correlations = {}
        insights = []
        
        # 健康记录与评估分数相关性
        if "health_records" in data_collection and "assessments" in data_collection:
            health_records = data_collection["health_records"]
            assessments = data_collection["assessments"]
            
            if health_records and assessments:
                # 简单示例：检查最近健康状况与评估分数的关系
                health_metrics = self._extract_latest_health_metrics(health_records)
                assessment_scores = self._extract_latest_assessment_scores(assessments)
                
                if health_metrics and assessment_scores:
                    health_assessment_corr = {
                        "type": "health_assessment",
                        "description": "健康指标与评估分数关系",
                        "health_metrics": health_metrics,
                        "assessment_scores": assessment_scores
                    }
                    
                    correlations["health_assessment"] = health_assessment_corr
                    
                    # 添加见解
                    if "pain_level" in health_metrics and "mobility" in assessment_scores:
                        pain = health_metrics["pain_level"]
                        mobility = assessment_scores["mobility"]
                        
                        if pain > 5 and mobility < 70:
                            insights.append("疼痛水平与活动能力存在明显负相关，疼痛水平高时活动能力下降")
        
        # 设备数据与运动记录相关性
        if "devices" in data_collection and "exercises" in data_collection:
            device_data = data_collection["devices"]
            exercise_data = data_collection["exercises"]
            
            if device_data and exercise_data:
                # 提取心率、步数等指标与运动时间的关系
                if any("heart_rate" in d for d in device_data):
                    device_exercise_corr = {
                        "type": "device_exercise",
                        "description": "设备监测指标与运动表现关系"
                    }
                    
                    correlations["device_exercise"] = device_exercise_corr
                    
                    # 添加见解
                    insights.append("设备监测数据可为运动表现分析提供客观依据")
        
        return {
            "correlations": correlations,
            "insights": insights
        }
    
    def _perform_trend_analysis(self, data_collection: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
        """执行趋势分析"""
        trends = {}
        insights = []
        
        # 评估分数趋势
        if "assessments" in data_collection:
            assessments = data_collection["assessments"]
            
            if assessments and len(assessments) >= 2:
                assessment_trends = self._analyze_assessment_trends(assessments)
                
                if assessment_trends:
                    trends["assessment"] = assessment_trends
                    
                    # 添加见解
                    for category, trend in assessment_trends.items():
                        if trend["direction"] == "上升":
                            insights.append(f"{category}评分呈上升趋势，康复进展良好")
                        elif trend["direction"] == "下降":
                            insights.append(f"{category}评分呈下降趋势，可能需要调整康复计划")
        
        # 运动完成情况趋势
        if "exercises" in data_collection:
            exercises = data_collection["exercises"]
            
            if exercises and len(exercises) >= 5:  # 至少需要5条记录
                exercise_trends = self._analyze_exercise_trends(exercises)
                
                if exercise_trends:
                    trends["exercise"] = exercise_trends
                    
                    # 添加见解
                    if "completion_rate" in exercise_trends:
                        rate = exercise_trends["completion_rate"]["latest_value"]
                        direction = exercise_trends["completion_rate"]["direction"]
                        
                        if rate < 0.7 and direction == "下降":
                            insights.append("运动完成率呈下降趋势且低于70%，建议重新评估运动计划难度")
        
        return {
            "trends": trends,
            "insights": insights
        }
    
    def _perform_pattern_analysis(self, data_collection: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
        """执行模式分析"""
        patterns = {}
        insights = []
        
        # 运动-恢复模式
        if "exercises" in data_collection and "health_records" in data_collection:
            exercises = data_collection["exercises"]
            health_records = data_collection["health_records"]
            
            if exercises and health_records:
                exercise_recovery_pattern = self._analyze_exercise_recovery_pattern(exercises, health_records)
                
                if exercise_recovery_pattern:
                    patterns["exercise_recovery"] = exercise_recovery_pattern
                    
                    # 添加见解
                    if "recovery_time" in exercise_recovery_pattern:
                        recovery_time = exercise_recovery_pattern["recovery_time"]
                        if recovery_time > 48:  # 大于48小时
                            insights.append("运动后恢复时间较长，建议调整运动强度或增加恢复措施")
        
        # 日常活动模式
        if "devices" in data_collection:
            device_data = data_collection["devices"]
            
            if device_data and len(device_data) >= 7:  # 至少一周的数据
                activity_pattern = self._analyze_activity_pattern(device_data)
                
                if activity_pattern:
                    patterns["activity"] = activity_pattern
                    
                    # 添加见解
                    if "weekday_weekend_diff" in activity_pattern:
                        diff = activity_pattern["weekday_weekend_diff"]
                        if abs(diff) > 0.3:  # 工作日和周末活动差异大于30%
                            insights.append("工作日和周末活动水平差异明显，建议保持更均衡的活动规律")
        
        return {
            "patterns": patterns,
            "insights": insights
        }
    
    def _extract_latest_health_metrics(self, health_records: List[Dict[str, Any]]) -> Dict[str, float]:
        """提取最新的健康指标"""
        if not health_records:
            return {}
            
        # 按记录日期排序
        sorted_records = sorted(health_records, key=lambda x: x.get("record_date"), reverse=True)
        
        latest_record = sorted_records[0]
        
        # 提取关键指标
        metrics = {}
        
        if "vital_signs" in latest_record:
            vital_signs = latest_record["vital_signs"]
            if "heart_rate" in vital_signs:
                metrics["heart_rate"] = vital_signs["heart_rate"]
            if "blood_pressure" in vital_signs:
                bp = vital_signs["blood_pressure"]
                if isinstance(bp, dict) and "systolic" in bp and "diastolic" in bp:
                    metrics["blood_pressure_systolic"] = bp["systolic"]
                    metrics["blood_pressure_diastolic"] = bp["diastolic"]
                    
        if "pain" in latest_record:
            metrics["pain_level"] = latest_record["pain"]
            
        if "fatigue" in latest_record:
            metrics["fatigue_level"] = latest_record["fatigue"]
            
        return metrics
    
    def _extract_latest_assessment_scores(self, assessments: List[Dict[str, Any]]) -> Dict[str, float]:
        """提取最新的评估分数"""
        if not assessments:
            return {}
            
        # 按评估日期排序
        sorted_assessments = sorted(assessments, key=lambda x: x.get("assessment_date"), reverse=True)
        
        latest_assessment = sorted_assessments[0]
        
        # 提取评估分数
        scores = {}
        
        if "scores" in latest_assessment:
            scores = latest_assessment["scores"]
            
        return scores
    
    def _analyze_assessment_trends(self, assessments: List[Dict[str, Any]]) -> Dict[str, Any]:
        """分析评估分数趋势"""
        # 按评估日期排序
        sorted_assessments = sorted(assessments, key=lambda x: x.get("assessment_date"))
        
        # 提取评估类别
        categories = set()
        for assessment in sorted_assessments:
            if "scores" in assessment:
                categories.update(assessment["scores"].keys())
                
        # 分析每个类别的趋势
        trends = {}
        
        for category in categories:
            values = []
            dates = []
            
            for assessment in sorted_assessments:
                if "scores" in assessment and category in assessment["scores"]:
                    values.append(assessment["scores"][category])
                    dates.append(assessment.get("assessment_date"))
            
            if len(values) >= 2:
                # 计算简单趋势
                first_value = values[0]
                last_value = values[-1]
                change = last_value - first_value
                
                # 确定趋势方向
                if abs(change) < 0.1 * first_value:  # 变化小于10%视为稳定
                    direction = "稳定"
                else:
                    direction = "上升" if change > 0 else "下降"
                    
                # 计算变化百分比
                percent_change = (change / first_value * 100) if first_value != 0 else 0
                
                trends[category] = {
                    "first_value": first_value,
                    "last_value": last_value,
                    "change": change,
                    "percent_change": percent_change,
                    "direction": direction,
                    "data_points": len(values)
                }
                
        return trends
    
    def _analyze_exercise_trends(self, exercises: List[Dict[str, Any]]) -> Dict[str, Any]:
        """分析运动完成情况趋势"""
        # 按记录日期排序
        sorted_exercises = sorted(exercises, key=lambda x: x.get("recorded_at"))
        
        # 划分为几个时间段
        segments = min(len(sorted_exercises) // 5, 3)  # 最多3个时间段
        segments = max(segments, 1)  # 至少1个时间段
        
        segment_size = len(sorted_exercises) // segments
        
        # 计算每个时间段的完成率
        completion_rates = []
        
        for i in range(segments):
            start_idx = i * segment_size
            end_idx = min((i + 1) * segment_size, len(sorted_exercises))
            
            segment_exercises = sorted_exercises[start_idx:end_idx]
            
            completed = sum(1 for ex in segment_exercises if ex.get("completed", False))
            total = len(segment_exercises)
            
            completion_rates.append(completed / total if total > 0 else 0)
        
        # 确定趋势方向
        if len(completion_rates) >= 2:
            first_rate = completion_rates[0]
            last_rate = completion_rates[-1]
            change = last_rate - first_rate
            
            if abs(change) < 0.05:  # 变化小于5%视为稳定
                direction = "稳定"
            else:
                direction = "上升" if change > 0 else "下降"
                
            return {
                "completion_rate": {
                    "values": completion_rates,
                    "first_value": first_rate,
                    "latest_value": last_rate,
                    "change": change,
                    "direction": direction
                }
            }
        
        return {}
    
    def _analyze_exercise_recovery_pattern(
        self, 
        exercises: List[Dict[str, Any]], 
        health_records: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """分析运动-恢复模式"""
        # 这是一个简化的实现，实际项目中可能需要更复杂的算法
        
        # 提取运动后疼痛和疲劳记录
        post_exercise_records = []
        
        for exercise in exercises:
            if not exercise.get("completed", False):
                continue
                
            exercise_time = exercise.get("recorded_at")
            if not exercise_time:
                continue
                
            # 查找运动后48小时内的健康记录
            for record in health_records:
                record_time = record.get("record_date")
                if not record_time:
                    continue
                    
                if isinstance(exercise_time, str):
                    exercise_time = datetime.fromisoformat(exercise_time.replace('Z', '+00:00'))
                if isinstance(record_time, str):
                    record_time = datetime.fromisoformat(record_time.replace('Z', '+00:00'))
                
                time_diff = (record_time - exercise_time).total_seconds() / 3600  # 小时
                
                if 0 < time_diff <= 48:  # 48小时内
                    post_exercise_records.append({
                        "exercise_time": exercise_time,
                        "record_time": record_time,
                        "time_diff_hours": time_diff,
                        "pain": record.get("pain"),
                        "fatigue": record.get("fatigue")
                    })
        
        if not post_exercise_records:
            return {}
            
        # 计算平均恢复时间和模式
        avg_recovery_time = 0
        pain_pattern = []
        fatigue_pattern = []
        
        for record in post_exercise_records:
            if record.get("pain") is not None and record.get("pain") <= 3:  # 疼痛恢复到低水平
                pain_pattern.append(record["time_diff_hours"])
                
            if record.get("fatigue") is not None and record.get("fatigue") <= 3:  # 疲劳恢复到低水平
                fatigue_pattern.append(record["time_diff_hours"])
        
        if pain_pattern:
            avg_pain_recovery = sum(pain_pattern) / len(pain_pattern)
        else:
            avg_pain_recovery = None
            
        if fatigue_pattern:
            avg_fatigue_recovery = sum(fatigue_pattern) / len(fatigue_pattern)
        else:
            avg_fatigue_recovery = None
            
        # 计算总体恢复时间
        recovery_times = pain_pattern + fatigue_pattern
        if recovery_times:
            avg_recovery_time = sum(recovery_times) / len(recovery_times)
        
        return {
            "recovery_time": avg_recovery_time,
            "pain_recovery_time": avg_pain_recovery,
            "fatigue_recovery_time": avg_fatigue_recovery,
            "sample_size": len(post_exercise_records)
        }
    
    def _analyze_activity_pattern(self, device_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """分析日常活动模式"""
        # 提取步数或活动数据
        activity_by_day = {}
        
        for record in device_data:
            timestamp = record.get("timestamp")
            if not timestamp:
                continue
                
            if isinstance(timestamp, str):
                timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                
            day = timestamp.strftime("%Y-%m-%d")
            weekday = timestamp.weekday()  # 0-6，0是周一
            
            steps = None
            
            if "steps" in record:
                steps = record["steps"]
            elif "activity" in record and "steps" in record["activity"]:
                steps = record["activity"]["steps"]
                
            if steps is not None:
                if day not in activity_by_day:
                    activity_by_day[day] = {
                        "date": day,
                        "weekday": weekday,
                        "is_weekend": weekday >= 5,  # 5和6是周末
                        "steps": 0
                    }
                    
                activity_by_day[day]["steps"] += steps
        
        if not activity_by_day:
            return {}
            
        # 分析工作日和周末的活动差异
        weekday_steps = []
        weekend_steps = []
        
        for day, data in activity_by_day.items():
            if data["is_weekend"]:
                weekend_steps.append(data["steps"])
            else:
                weekday_steps.append(data["steps"])
                
        if weekday_steps and weekend_steps:
            avg_weekday = sum(weekday_steps) / len(weekday_steps)
            avg_weekend = sum(weekend_steps) / len(weekend_steps)
            
            # 计算差异百分比
            weekday_weekend_diff = (avg_weekend - avg_weekday) / avg_weekday if avg_weekday > 0 else 0
            
            return {
                "avg_weekday_steps": avg_weekday,
                "avg_weekend_steps": avg_weekend,
                "weekday_weekend_diff": weekday_weekend_diff,
                "weekday_samples": len(weekday_steps),
                "weekend_samples": len(weekend_steps)
            }
        
        return {}
    
    def _generate_analysis_summary(
        self, 
        analysis_result: Dict[str, Any],
        analysis_type: str,
        medical_records: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, str]:
        """生成分析摘要"""
        summary = {}
        
        # 提取关键见解
        all_insights = []
        
        if analysis_type == "comprehensive" or analysis_type == "all":
            if "correlation" in analysis_result and "insights" in analysis_result["correlation"]:
                all_insights.extend(analysis_result["correlation"]["insights"])
                
            if "trend" in analysis_result and "insights" in analysis_result["trend"]:
                all_insights.extend(analysis_result["trend"]["insights"])
                
            if "pattern" in analysis_result and "insights" in analysis_result["pattern"]:
                all_insights.extend(analysis_result["pattern"]["insights"])
        elif "insights" in analysis_result:
            all_insights.extend(analysis_result["insights"])
        
        # 生成主要摘要
        main_summary = "多模态数据分析结果"
        
        if all_insights:
            main_summary += "主要发现："
            
            # 限制摘要长度，最多显示3条见解
            for i, insight in enumerate(all_insights[:3]):
                main_summary += f"\n{i+1}. {insight}"
                
            if len(all_insights) > 3:
                main_summary += f"\n...以及{len(all_insights) - 3}条其他发现。"
        
        summary["main"] = main_summary
        
        # 根据分析类型添加特定摘要
        if analysis_type == "correlation" or analysis_type == "comprehensive" or analysis_type == "all":
            corr_summary = "相关性分析：未发现明显相关模式。"
            
            if "correlation" in analysis_result and "correlations" in analysis_result["correlation"]:
                correlations = analysis_result["correlation"]["correlations"]
                if correlations:
                    corr_summary = "相关性分析：发现数据间存在关联模式，"
                    if "health_assessment" in correlations:
                        corr_summary += "健康指标与评估分数显示相关性。"
            
            summary["correlation"] = corr_summary
            
        if analysis_type == "trend" or analysis_type == "comprehensive" or analysis_type == "all":
            trend_summary = "趋势分析：数据量不足，无法确定明确趋势。"
            
            if "trend" in analysis_result and "trends" in analysis_result["trend"]:
                trends = analysis_result["trend"]["trends"]
                if trends:
                    trend_summary = "趋势分析："
                    if "assessment" in trends:
                        improving_categories = []
                        declining_categories = []
                        stable_categories = []
                        
                        for category, data in trends["assessment"].items():
                            if data["direction"] == "上升":
                                improving_categories.append(category)
                            elif data["direction"] == "下降":
                                declining_categories.append(category)
                            else:
                                stable_categories.append(category)
                                
                        if improving_categories:
                            trend_summary += f"{', '.join(improving_categories)}评分呈上升趋势；"
                        if declining_categories:
                            trend_summary += f"{', '.join(declining_categories)}评分呈下降趋势；"
                        if stable_categories:
                            trend_summary += f"{', '.join(stable_categories)}评分保持稳定。"
            
            summary["trend"] = trend_summary
            
        if analysis_type == "pattern" or analysis_type == "comprehensive" or analysis_type == "all":
            pattern_summary = "模式分析：未发现明显活动与恢复模式。"
            
            if "pattern" in analysis_result and "patterns" in analysis_result["pattern"]:
                patterns = analysis_result["pattern"]["patterns"]
                if patterns and "exercise_recovery" in patterns:
                    recovery = patterns["exercise_recovery"]
                    if "recovery_time" in recovery and recovery["recovery_time"]:
                        hours = recovery["recovery_time"]
                        pattern_summary = f"模式分析：运动后平均恢复时间约{hours:.1f}小时。"
            
            summary["pattern"] = pattern_summary
        
        return summary
        
    async def _save_analysis_result(
        self,
        patient_id: str,
        analysis_type: str,
        data_sources: List[str],
        analysis_result: Dict[str, Any],
        summary: Dict[str, str],
        start_date: datetime,
        end_date: datetime
    ) -> str:
        """保存分析结果到数据库"""
        # 创建分析记录
        analysis_record = {
            "patient_id": patient_id,
            "analysis_type": analysis_type,
            "data_sources": data_sources,
            "period": {
                "start_date": start_date,
                "end_date": end_date
            },
            "summary": summary,
            "results": analysis_result,
            "created_at": datetime.utcnow()
        }
        
        result = await self.analysis_collection.insert_one(analysis_record)
        return str(result.inserted_id) 