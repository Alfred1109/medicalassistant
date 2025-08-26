"""
报表调度服务
处理报表的自动生成和分发
"""
from typing import List, Optional, Dict, Any, Union
from datetime import datetime, timedelta
import asyncio
import logging
from bson import ObjectId
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
import tempfile
import os

from ..db.mongodb import get_db
from ..services.device_analysis_service import device_analysis_service
from ..core.config import settings

logger = logging.getLogger(__name__)

class ReportSchedulerService:
    """报表调度服务，负责管理报表的自动生成和分发"""
    
    def __init__(self):
        """初始化报表调度服务"""
        self.db = None
        self.is_running = False
        self._scheduler_task = None
    
    async def start(self):
        """启动调度服务"""
        if self.is_running:
            return
        
        self.db = await get_db()
        self.is_running = True
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        logger.info("报表调度服务已启动")
    
    async def stop(self):
        """停止调度服务"""
        if not self.is_running:
            return
        
        self.is_running = False
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
            self._scheduler_task = None
        
        logger.info("报表调度服务已停止")
    
    async def _scheduler_loop(self):
        """调度循环，检查并执行到期的报表任务"""
        while self.is_running:
            try:
                now = datetime.utcnow()
                
                # 查找需要执行的任务
                query = {
                    "enabled": True,
                    "nextRunTime": {"$lte": now}
                }
                
                async for schedule in self.db.report_schedules.find(query):
                    # 创建单独的任务执行报表生成和发送
                    asyncio.create_task(self._process_schedule(schedule))
                    
                    # 更新下次执行时间
                    await self._update_next_run_time(schedule)
                
                # 每分钟检查一次
                await asyncio.sleep(60)
            except Exception as e:
                logger.error(f"调度循环发生错误: {str(e)}")
                await asyncio.sleep(60)  # 发生错误时也等待一分钟后继续
    
    async def _process_schedule(self, schedule: Dict[str, Any]):
        """处理单个调度任务"""
        schedule_id = str(schedule["_id"])
        report_id = schedule.get("reportId")
        
        logger.info(f"开始执行调度任务: {schedule_id}, 报表: {report_id}")
        
        try:
            # 获取报表配置
            report_config = await self.db.reports.find_one({"_id": ObjectId(report_id)})
            if not report_config:
                raise ValueError(f"找不到报表配置: {report_id}")
            
            # 生成报表数据
            report_data = await self._generate_report(report_config)
            
            # 根据格式导出报表
            report_format = schedule.get("format", "pdf")
            report_file = await self._export_report(report_data, report_format, report_config.get("title", "报表"))
            
            # 发送邮件
            if schedule.get("recipients") and len(schedule.get("recipients")) > 0:
                await self._send_report_email(
                    recipients=schedule["recipients"],
                    subject=f"自动报表: {report_config.get('title', '数据分析报表')}",
                    report_file=report_file,
                    report_format=report_format,
                    schedule_name=schedule.get("name", "自动报表"),
                    report_name=report_config.get("title", "数据分析报表")
                )
            
            # 更新执行状态
            await self.db.report_schedules.update_one(
                {"_id": ObjectId(schedule_id)},
                {"$set": {
                    "lastRunTime": datetime.utcnow(),
                    "lastRunStatus": "success"
                }}
            )
            
            logger.info(f"调度任务执行成功: {schedule_id}")
        except Exception as e:
            logger.error(f"调度任务执行失败: {schedule_id}, 错误: {str(e)}")
            
            # 更新执行状态为失败
            await self.db.report_schedules.update_one(
                {"_id": ObjectId(schedule_id)},
                {"$set": {
                    "lastRunTime": datetime.utcnow(),
                    "lastRunStatus": "error"
                }}
            )
    
    async def _update_next_run_time(self, schedule: Dict[str, Any]):
        """更新调度任务的下次执行时间"""
        schedule_id = schedule["_id"]
        frequency = schedule.get("frequency")
        now = datetime.utcnow()
        
        if frequency == "once":
            # 一次性任务执行后禁用
            await self.db.report_schedules.update_one(
                {"_id": schedule_id},
                {"$set": {"enabled": False}}
            )
            return
        
        # 计算下次执行时间
        next_run_time = None
        
        if frequency == "daily":
            # 获取配置的小时和分钟
            time_parts = schedule.get("time", "00:00").split(":")
            hour = int(time_parts[0])
            minute = int(time_parts[1])
            
            next_run_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if next_run_time <= now:
                next_run_time += timedelta(days=1)
        
        elif frequency == "weekly":
            weekday = schedule.get("weekday", 0)  # 0-6, 周日为0
            time_parts = schedule.get("time", "00:00").split(":")
            hour = int(time_parts[0])
            minute = int(time_parts[1])
            
            # 计算当前周几
            current_weekday = now.weekday()
            # 调整为周日为0的系统
            current_weekday = (current_weekday + 1) % 7
            
            # 计算距离下次执行的天数
            days_until_next = (weekday - current_weekday) % 7
            if days_until_next == 0:
                # 如果是同一天，但时间已过，则设为下周
                next_run_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if next_run_time <= now:
                    days_until_next = 7
            
            next_run_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            next_run_time += timedelta(days=days_until_next)
        
        elif frequency == "monthly":
            month_day = schedule.get("monthDay", 1)  # 每月几号
            time_parts = schedule.get("time", "00:00").split(":")
            hour = int(time_parts[0])
            minute = int(time_parts[1])
            
            # 设置为本月指定日期
            next_run_time = now.replace(day=min(month_day, 28), hour=hour, minute=minute, second=0, microsecond=0)
            
            # 如果已过，则设为下月
            if next_run_time <= now:
                if now.month == 12:
                    next_run_time = next_run_time.replace(year=now.year+1, month=1)
                else:
                    next_run_time = next_run_time.replace(month=now.month+1)
        
        if next_run_time:
            await self.db.report_schedules.update_one(
                {"_id": schedule_id},
                {"$set": {"nextRunTime": next_run_time}}
            )
    
    async def _generate_report(self, report_config: Dict[str, Any]) -> Dict[str, Any]:
        """根据报表配置生成报表数据"""
        charts = report_config.get("charts", [])
        report_data = {
            "title": report_config.get("title", "数据分析报表"),
            "description": report_config.get("description", ""),
            "generated_at": datetime.utcnow(),
            "charts_data": []
        }
        
        for chart in charts:
            chart_type = chart.get("type")
            data_type = chart.get("dataType")
            time_range = chart.get("timeRange")
            
            # 根据图表类型和数据类型获取数据
            chart_data = await self._get_chart_data(chart_type, data_type, time_range)
            
            report_data["charts_data"].append({
                "title": chart.get("title", "图表"),
                "type": chart_type,
                "data": chart_data
            })
        
        return report_data
    
    async def _get_chart_data(self, chart_type: str, data_type: str, time_range: str) -> List[Dict[str, Any]]:
        """获取图表数据"""
        # 这里应该根据不同的数据类型调用相应的服务获取数据
        # 下面是一个示例实现
        
        days = self._time_range_to_days(time_range)
        
        if data_type == "patient":
            # 获取患者相关数据
            return await self._get_patient_stats(days)
        elif data_type == "device":
            # 获取设备相关数据
            return await self._get_device_stats(days)
        elif data_type == "rehabilitation":
            # 获取康复训练相关数据
            return await self._get_rehabilitation_stats(days)
        else:
            # 默认返回空数据
            return []
    
    def _time_range_to_days(self, time_range: str) -> int:
        """将时间范围转换为天数"""
        if time_range == "day":
            return 1
        elif time_range == "week":
            return 7
        elif time_range == "month":
            return 30
        elif time_range == "quarter":
            return 90
        elif time_range == "year":
            return 365
        else:
            return 30  # 默认为一个月
    
    async def _get_patient_stats(self, days: int) -> List[Dict[str, Any]]:
        """获取患者统计数据"""
        start_date = datetime.utcnow() - timedelta(days=days)
        
        pipeline = [
            {"$match": {"created_at": {"$gte": start_date}}},
            {"$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
                "count": {"$sum": 1}
            }},
            {"$sort": {"_id": 1}}
        ]
        
        result = []
        async for doc in self.db.patients.aggregate(pipeline):
            result.append({
                "date": doc["_id"],
                "value": doc["count"]
            })
        
        return result
    
    async def _get_device_stats(self, days: int) -> List[Dict[str, Any]]:
        """获取设备统计数据"""
        start_date = datetime.utcnow() - timedelta(days=days)
        
        pipeline = [
            {"$match": {"timestamp": {"$gte": start_date}}},
            {"$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp"}},
                "count": {"$sum": 1},
                "avg_value": {"$avg": "$value"}
            }},
            {"$sort": {"_id": 1}}
        ]
        
        result = []
        async for doc in self.db.device_data.aggregate(pipeline):
            result.append({
                "date": doc["_id"],
                "count": doc["count"],
                "average": doc["avg_value"]
            })
        
        return result
    
    async def _get_rehabilitation_stats(self, days: int) -> List[Dict[str, Any]]:
        """获取康复训练统计数据"""
        start_date = datetime.utcnow() - timedelta(days=days)
        
        pipeline = [
            {"$match": {"created_at": {"$gte": start_date}}},
            {"$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
                "count": {"$sum": 1},
                "avg_duration": {"$avg": "$duration"},
                "avg_score": {"$avg": "$score"}
            }},
            {"$sort": {"_id": 1}}
        ]
        
        result = []
        async for doc in self.db.rehabilitation_sessions.aggregate(pipeline):
            result.append({
                "date": doc["_id"],
                "count": doc["count"],
                "avgDuration": doc["avg_duration"],
                "avgScore": doc["avg_score"]
            })
        
        return result
    
    async def _export_report(self, report_data: Dict[str, Any], format: str, title: str) -> str:
        """导出报表为指定格式的文件"""
        # 在实际应用中，应该使用专业的报表生成库，如ReportLab或WeasyPrint等
        # 这里简化处理，将数据导出为JSON文件（实际应用中应生成PDF/Excel）
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{format}") as temp:
            if format == "pdf":
                # TODO: 实现PDF生成
                # 简化处理，生成文本文件
                import json
                temp.write(json.dumps(report_data, default=str).encode('utf-8'))
            elif format == "excel":
                # TODO: 实现Excel生成
                # 简化处理，生成CSV格式
                import csv
                
                # 写入基本信息
                temp.write(f"标题: {title}\n".encode('utf-8'))
                temp.write(f"生成时间: {report_data['generated_at']}\n\n".encode('utf-8'))
                
                # 写入图表数据
                for chart in report_data["charts_data"]:
                    temp.write(f"{chart['title']}\n".encode('utf-8'))
                    
                    # 获取所有可能的列
                    columns = set()
                    for item in chart["data"]:
                        columns.update(item.keys())
                    
                    # 写入列头
                    temp.write((",".join(columns) + "\n").encode('utf-8'))
                    
                    # 写入数据行
                    for item in chart["data"]:
                        row = [str(item.get(col, "")) for col in columns]
                        temp.write((",".join(row) + "\n").encode('utf-8'))
                    
                    temp.write("\n".encode('utf-8'))
            else:  # html 或其他
                # 生成简单的HTML报表
                html = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="UTF-8">
                    <title>{title}</title>
                    <style>
                        body {{ font-family: Arial, sans-serif; margin: 20px; }}
                        h1 {{ color: #333; }}
                        table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
                        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                        th {{ background-color: #f2f2f2; }}
                        .chart-container {{ margin-bottom: 30px; }}
                    </style>
                </head>
                <body>
                    <h1>{title}</h1>
                    <p>生成时间: {report_data['generated_at']}</p>
                    <p>{report_data.get('description', '')}</p>
                """
                
                for chart in report_data["charts_data"]:
                    html += f"""
                    <div class="chart-container">
                        <h2>{chart['title']}</h2>
                        <table>
                            <thead>
                                <tr>
                    """
                    
                    # 获取所有可能的列
                    columns = set()
                    for item in chart["data"]:
                        columns.update(item.keys())
                    
                    # 写入列头
                    for col in columns:
                        html += f"<th>{col}</th>"
                    html += "</tr></thead><tbody>"
                    
                    # 写入数据行
                    for item in chart["data"]:
                        html += "<tr>"
                        for col in columns:
                            html += f"<td>{item.get(col, '')}</td>"
                        html += "</tr>"
                    
                    html += "</tbody></table></div>"
                
                html += "</body></html>"
                temp.write(html.encode('utf-8'))
            
            return temp.name
    
    async def _send_report_email(self, recipients: List[str], subject: str, report_file: str, 
                                report_format: str, schedule_name: str, report_name: str):
        """发送报表邮件"""
        if not settings.SMTP_HOST or not settings.SMTP_PORT:
            logger.error("SMTP配置缺失，无法发送邮件")
            return
        
        try:
            # 创建多部分邮件
            msg = MIMEMultipart()
            msg['From'] = settings.SMTP_SENDER
            msg['To'] = ", ".join(recipients)
            msg['Subject'] = subject
            
            # 添加邮件正文
            body = f"""
            <html>
            <body>
                <h2>自动报表: {report_name}</h2>
                <p>您订阅的自动报表 "{schedule_name}" 已生成，请查看附件。</p>
                <p>报表生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
                <p>此邮件由系统自动发送，请勿回复。</p>
            </body>
            </html>
            """
            msg.attach(MIMEText(body, 'html'))
            
            # 添加附件
            with open(report_file, "rb") as file:
                attachment = MIMEApplication(file.read())
                file_extension = report_format.lower()
                attachment.add_header(
                    "Content-Disposition", 
                    f"attachment; filename={report_name}_{datetime.now().strftime('%Y%m%d')}.{file_extension}"
                )
                msg.attach(attachment)
            
            # 连接SMTP服务器并发送
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
                if settings.SMTP_USE_TLS:
                    server.starttls()
                
                if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                    server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                
                server.send_message(msg)
            
            logger.info(f"已成功发送报表邮件至 {len(recipients)} 位接收者")
        except Exception as e:
            logger.error(f"发送邮件失败: {str(e)}")
        finally:
            # 删除临时文件
            try:
                os.unlink(report_file)
            except:
                pass
    
    async def create_schedule(self, schedule_data: Dict[str, Any]) -> str:
        """创建新的报表调度计划"""
        self.db = await get_db()
        
        # 设置创建时间
        schedule_data["createdAt"] = datetime.utcnow()
        
        # 设置下次运行时间
        if schedule_data.get("frequency") == "once":
            schedule_data["nextRunTime"] = schedule_data.get("nextRunTime", datetime.utcnow())
        else:
            # 根据频率设置下次运行时间
            time_parts = schedule_data.get("time", "00:00").split(":")
            hour = int(time_parts[0])
            minute = int(time_parts[1])
            
            next_run = datetime.utcnow().replace(hour=hour, minute=minute, second=0, microsecond=0)
            
            if schedule_data.get("frequency") == "daily":
                if next_run <= datetime.utcnow():
                    next_run += timedelta(days=1)
            elif schedule_data.get("frequency") == "weekly":
                weekday = schedule_data.get("weekday", 0)
                days_until = (weekday - next_run.weekday() - 1) % 7
                if days_until == 0 and next_run <= datetime.utcnow():
                    days_until = 7
                next_run += timedelta(days=days_until)
            elif schedule_data.get("frequency") == "monthly":
                month_day = schedule_data.get("monthDay", 1)
                next_run = next_run.replace(day=min(month_day, 28))
                if next_run <= datetime.utcnow():
                    if next_run.month == 12:
                        next_run = next_run.replace(year=next_run.year+1, month=1)
                    else:
                        next_run = next_run.replace(month=next_run.month+1)
            
            schedule_data["nextRunTime"] = next_run
        
        # 插入记录
        result = await self.db.report_schedules.insert_one(schedule_data)
        return str(result.inserted_id)
    
    async def update_schedule(self, schedule_id: str, schedule_data: Dict[str, Any]) -> bool:
        """更新报表调度计划"""
        self.db = await get_db()
        
        # 移除不允许更新的字段
        for field in ["_id", "createdAt", "lastRunTime", "lastRunStatus"]:
            if field in schedule_data:
                del schedule_data[field]
        
        # 如果修改了频率相关设置，更新下次运行时间
        frequency_fields = ["frequency", "weekday", "monthDay", "time", "nextRunTime"]
        needs_update_next_run = any(field in schedule_data for field in frequency_fields)
        
        if needs_update_next_run:
            # 获取完整的计划数据
            current_schedule = await self.db.report_schedules.find_one({"_id": ObjectId(schedule_id)})
            if not current_schedule:
                return False
            
            # 合并新的数据
            updated_schedule = {**current_schedule, **schedule_data}
            
            # 根据新的频率设置计算下次运行时间
            if updated_schedule.get("frequency") == "once":
                if "nextRunTime" in schedule_data:
                    updated_schedule["nextRunTime"] = schedule_data["nextRunTime"]
                else:
                    updated_schedule["nextRunTime"] = datetime.utcnow()
            else:
                # 根据频率设置下次运行时间
                time_parts = updated_schedule.get("time", "00:00").split(":")
                hour = int(time_parts[0])
                minute = int(time_parts[1])
                
                next_run = datetime.utcnow().replace(hour=hour, minute=minute, second=0, microsecond=0)
                
                if updated_schedule.get("frequency") == "daily":
                    if next_run <= datetime.utcnow():
                        next_run += timedelta(days=1)
                elif updated_schedule.get("frequency") == "weekly":
                    weekday = updated_schedule.get("weekday", 0)
                    days_until = (weekday - next_run.weekday() - 1) % 7
                    if days_until == 0 and next_run <= datetime.utcnow():
                        days_until = 7
                    next_run += timedelta(days=days_until)
                elif updated_schedule.get("frequency") == "monthly":
                    month_day = updated_schedule.get("monthDay", 1)
                    next_run = next_run.replace(day=min(month_day, 28))
                    if next_run <= datetime.utcnow():
                        if next_run.month == 12:
                            next_run = next_run.replace(year=next_run.year+1, month=1)
                        else:
                            next_run = next_run.replace(month=next_run.month+1)
                
                schedule_data["nextRunTime"] = next_run
        
        # 更新记录
        result = await self.db.report_schedules.update_one(
            {"_id": ObjectId(schedule_id)},
            {"$set": schedule_data}
        )
        
        return result.modified_count > 0
    
    async def delete_schedule(self, schedule_id: str) -> bool:
        """删除报表调度计划"""
        self.db = await get_db()
        result = await self.db.report_schedules.delete_one({"_id": ObjectId(schedule_id)})
        return result.deleted_count > 0
    
    async def get_schedule(self, schedule_id: str) -> Optional[Dict[str, Any]]:
        """获取单个报表调度计划"""
        self.db = await get_db()
        schedule = await self.db.report_schedules.find_one({"_id": ObjectId(schedule_id)})
        if schedule:
            schedule["_id"] = str(schedule["_id"])
        return schedule
    
    async def get_schedules(self, user_id: Optional[str] = None, report_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取报表调度计划列表"""
        self.db = await get_db()
        
        query = {}
        if user_id:
            query["createdBy"] = user_id
        if report_id:
            query["reportId"] = report_id
        
        schedules = []
        async for schedule in self.db.report_schedules.find(query).sort("createdAt", -1):
            schedule["_id"] = str(schedule["_id"])
            schedules.append(schedule)
        
        return schedules
    
    async def toggle_schedule(self, schedule_id: str, enabled: bool) -> bool:
        """启用或禁用报表调度计划"""
        self.db = await get_db()
        result = await self.db.report_schedules.update_one(
            {"_id": ObjectId(schedule_id)},
            {"$set": {"enabled": enabled}}
        )
        return result.modified_count > 0


# 创建服务实例
report_scheduler_service = ReportSchedulerService() 