import asyncio
import json
from datetime import datetime, timedelta
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
import random

from app.core.config import settings

async def init_dashboard_data():
    """初始化仪表盘数据，用于测试"""
    print("开始初始化仪表盘数据...")
    
    # 连接数据库
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.MONGODB_DB_NAME]
    
    # 获取用户列表
    users = await db.users.find().to_list(length=100)
    
    if not users:
        print("错误: 未找到任何用户，请先初始化用户数据")
        return
    
    # 找到医生和患者
    doctors = [user for user in users if user.get('role') == 'doctor']
    patients = [user for user in users if user.get('role') == 'patient']
    
    if not doctors:
        print("错误: 未找到任何医生用户")
        return
    
    if not patients:
        print("错误: 未找到任何患者用户")
        return
    
    print(f"找到 {len(doctors)} 名医生和 {len(patients)} 名患者")
    
    # 生成健康指标数据
    await generate_health_metrics(db, patients)
    
    # 生成待办事项
    await generate_todo_items(db, patients)
    
    # 生成康复进度
    await generate_rehab_progress(db, patients, doctors)
    
    client.close()
    print("仪表盘数据初始化完成")

async def generate_health_metrics(db, patients):
    """生成健康指标数据"""
    print("生成健康指标数据...")
    
    # 定义指标类型
    metric_types = [
        {"name": "心率", "unit": "次/分", "min": 60, "max": 100, "trend_range": (-3, 5)},
        {"name": "血压", "unit": "mmHg", "pattern": "SYS/DIA", "sys_min": 100, "sys_max": 140, "dia_min": 60, "dia_max": 90, "trend_range": (-2, 3)},
        {"name": "步数", "unit": "步/天", "min": 2000, "max": 12000, "trend_range": (-10, 20)},
        {"name": "睡眠", "unit": "小时", "min": 5, "max": 9, "trend_range": (-5, 10)}
    ]
    
    # 清空现有健康指标集合
    await db.health_metrics.delete_many({})
    
    # 为每个患者生成健康指标
    health_metrics = []
    for patient in patients:
        patient_id = str(patient["_id"])
        
        for metric_type in metric_types:
            # 生成随机值
            if metric_type["name"] == "血压":
                sys = random.randint(metric_type["sys_min"], metric_type["sys_max"])
                dia = random.randint(metric_type["dia_min"], metric_type["dia_max"])
                value = f"{sys}/{dia}"
            else:
                if metric_type["name"] == "睡眠":
                    # 睡眠时间有小数点
                    value = str(round(random.uniform(metric_type["min"], metric_type["max"]), 1))
                else:
                    value = str(random.randint(metric_type["min"], metric_type["max"]))
                    # 步数添加千分位分隔符
                    if metric_type["name"] == "步数":
                        value = f"{int(value):,}"
            
            # 生成趋势
            trend_change = random.randint(metric_type["trend_range"][0], metric_type["trend_range"][1])
            trend = f"{'+' if trend_change > 0 else ''}{trend_change}%"
            
            # 确定状态
            if metric_type["name"] == "血压":
                sys = int(value.split("/")[0])
                if sys < 110 or sys > 130:
                    status = "warning" if sys < 100 or sys > 140 else "normal"
                else:
                    status = "good"
            elif metric_type["name"] == "心率":
                hr = float(value)
                if hr < 60 or hr > 90:
                    status = "warning" if hr < 50 or hr > 100 else "normal"
                else:
                    status = "good"
            elif metric_type["name"] == "步数":
                steps = int(value.replace(",", ""))
                if steps < 3000:
                    status = "warning"
                elif steps > 8000:
                    status = "good"
                else:
                    status = "normal"
            else:  # 睡眠
                sleep = float(value)
                if sleep < 6 or sleep > 8:
                    status = "warning" if sleep < 5 or sleep > 9 else "normal"
                else:
                    status = "good"
            
            # 创建健康指标记录
            health_metrics.append({
                "_id": ObjectId(),
                "name": metric_type["name"],
                "value": value,
                "unit": metric_type["unit"],
                "status": status,
                "trend": trend,
                "user_id": patient_id,
                "timestamp": datetime.now() - timedelta(minutes=random.randint(0, 120))
            })
    
    # 插入健康指标数据
    if health_metrics:
        result = await db.health_metrics.insert_many(health_metrics)
        print(f"成功插入 {len(result.inserted_ids)} 条健康指标数据")
    else:
        print("没有健康指标数据被插入")

async def generate_todo_items(db, patients):
    """生成待办事项"""
    print("生成待办事项...")
    
    # 定义待办事项类型
    todo_types = [
        {"title": "血压记录", "description": "请完成今日的血压测量记录", "due": "今天", "important": True},
        {"title": "服药提醒", "description": "降压药 - 每日2次", "due": "12:30", "important": True},
        {"title": "康复练习", "description": "完成下肢力量训练", "due": "今天", "important": False},
        {"title": "睡眠日记", "description": "记录昨晚睡眠情况", "due": "今天", "important": False},
        {"title": "体重记录", "description": "记录今日体重", "due": "晚上", "important": False},
        {"title": "复诊预约", "description": "与王医生复诊", "due": "明天 14:00", "important": True},
    ]
    
    # 清空现有待办事项集合
    await db.todo_items.delete_many({})
    
    # 为每个患者生成待办事项
    todo_items = []
    for patient in patients:
        patient_id = str(patient["_id"])
        
        # 随机选择4-6个待办事项
        num_todos = random.randint(4, 6)
        selected_todos = random.sample(todo_types, num_todos)
        
        for i, todo_type in enumerate(selected_todos):
            # 随机完成状态（25%概率已完成）
            completed = random.random() < 0.25
            
            # 创建待办事项记录
            todo_items.append({
                "_id": ObjectId(),
                "title": todo_type["title"],
                "description": todo_type["description"],
                "due": todo_type["due"],
                "important": todo_type["important"],
                "completed": completed,
                "user_id": patient_id,
                "timestamp": datetime.now() - timedelta(hours=random.randint(0, 24))
            })
    
    # 插入待办事项数据
    if todo_items:
        result = await db.todo_items.insert_many(todo_items)
        print(f"成功插入 {len(result.inserted_ids)} 条待办事项数据")
    else:
        print("没有待办事项数据被插入")

async def generate_rehab_progress(db, patients, doctors):
    """生成康复进度数据"""
    print("生成康复进度数据...")
    
    # 定义康复计划类型
    rehab_plans = [
        {"plan": "下肢功能恢复计划", "exercises": [
            {"name": "下肢伸展", "completed": True}, 
            {"name": "平衡训练", "completed": True},
            {"name": "步态训练", "completed": False},
            {"name": "力量训练", "completed": False}
        ]},
        {"plan": "上肢功能康复计划", "exercises": [
            {"name": "肩部活动", "completed": True}, 
            {"name": "握力训练", "completed": True},
            {"name": "手指灵活性练习", "completed": False},
            {"name": "肘部强化", "completed": False}
        ]},
        {"plan": "脊柱康复训练计划", "exercises": [
            {"name": "腰背伸展", "completed": True}, 
            {"name": "核心肌群强化", "completed": False},
            {"name": "姿势纠正训练", "completed": False},
            {"name": "脊柱稳定性练习", "completed": False}
        ]},
    ]
    
    # 定义下一次康复时间选项
    next_sessions = ["今天 15:00", "明天 10:30", "明天 15:00", "后天 09:00", "周五 14:00"]
    
    # 清空现有康复进度集合
    await db.rehab_progress.delete_many({})
    
    # 为每个患者生成康复进度
    rehab_progress_records = []
    for patient in patients:
        patient_id = str(patient["_id"])
        
        # 随机选择一个医生
        doctor = random.choice(doctors)
        doctor_id = str(doctor["_id"])
        
        # 随机选择一个康复计划
        plan = random.choice(rehab_plans)
        
        # 根据已完成的训练项目计算进度
        completed_count = sum(1 for exercise in plan["exercises"] if exercise["completed"])
        total_count = len(plan["exercises"])
        progress = int((completed_count / total_count) * 100)
        
        # 随机选择下次康复时间
        next_session = random.choice(next_sessions)
        
        # 创建康复进度记录
        rehab_progress_records.append({
            "_id": ObjectId(),
            "plan": plan["plan"],
            "progress": progress,
            "next_session": next_session,
            "user_id": patient_id,
            "doctor_id": doctor_id,
            "exercises": plan["exercises"],
            "timestamp": datetime.now() - timedelta(days=random.randint(0, 7))
        })
    
    # 插入康复进度数据
    if rehab_progress_records:
        result = await db.rehab_progress.insert_many(rehab_progress_records)
        print(f"成功插入 {len(result.inserted_ids)} 条康复进度数据")
    else:
        print("没有康复进度数据被插入")

if __name__ == "__main__":
    asyncio.run(init_dashboard_data()) 