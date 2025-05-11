"""
测试康复计划数据生成脚本
用于向MongoDB数据库添加模拟康复计划数据
"""
import asyncio
import random
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings
from datetime import datetime, timedelta
from bson import ObjectId

# 康复计划模板
REHAB_PLAN_TEMPLATES = [
    {
        "name": "腰椎间盘突出康复计划",
        "description": "针对腰椎间盘突出患者的综合康复计划，包含运动疗法、物理治疗和日常活动指导。",
        "duration_weeks": 8,
        "condition": "腰椎间盘突出",
        "exercises": [
            {
                "name": "麦肯基伸展",
                "frequency": "每日3次",
                "sets": 3,
                "reps": 10,
                "duration_minutes": 10,
                "description": "俯卧位，双手撑地，上半身慢慢抬起，保持腰部放松。",
                "media_url": "https://example.com/exercises/mckenzie.mp4"
            },
            {
                "name": "核心稳定训练",
                "frequency": "每日1次",
                "sets": 3,
                "reps": 15,
                "duration_minutes": 15,
                "description": "平板支撑，保持核心稳定，维持正确姿势。",
                "media_url": "https://example.com/exercises/core_stability.mp4"
            },
            {
                "name": "髋关节灵活性训练",
                "frequency": "每周5次",
                "sets": 2,
                "reps": 12,
                "duration_minutes": 10,
                "description": "仰卧位，双膝弯曲，慢慢转动髋部。",
                "media_url": "https://example.com/exercises/hip_mobility.mp4"
            }
        ],
        "physical_therapy": [
            {
                "name": "腰椎牵引",
                "frequency": "每周3次",
                "duration_minutes": 20,
                "description": "使用腰椎牵引设备，减轻椎间盘压力。"
            },
            {
                "name": "热敷理疗",
                "frequency": "每日2次",
                "duration_minutes": 15,
                "description": "使用热敷垫热敷腰部，缓解肌肉紧张。"
            }
        ],
        "daily_activities": [
            "避免长时间坐立，每小时起身活动5分钟",
            "保持正确坐姿，使用腰靠",
            "避免弯腰搬重物，正确姿势弯腰"
        ],
        "progress_metrics": [
            "疼痛评分(0-10)",
            "活动范围角度",
            "日常活动能力"
        ]
    },
    {
        "name": "膝关节韧带损伤康复计划",
        "description": "针对膝关节韧带损伤患者的康复训练计划，逐步恢复关节稳定性和肌肉力量。",
        "duration_weeks": 12,
        "condition": "膝关节韧带损伤",
        "exercises": [
            {
                "name": "直腿抬高",
                "frequency": "每日2次",
                "sets": 3,
                "reps": 15,
                "duration_minutes": 10,
                "description": "仰卧位，一侧腿伸直抬高，另一侧腿弯曲。",
                "media_url": "https://example.com/exercises/straight_leg_raise.mp4"
            },
            {
                "name": "坐姿膝关节伸展",
                "frequency": "每日2次",
                "sets": 3,
                "reps": 12,
                "duration_minutes": 12,
                "description": "坐椅上，慢慢伸直膝关节，维持几秒后放下。",
                "media_url": "https://example.com/exercises/seated_knee_extension.mp4"
            },
            {
                "name": "站立平衡训练",
                "frequency": "每日1次",
                "sets": 2,
                "reps": 5,
                "duration_minutes": 10,
                "description": "单腿站立，保持平衡，可逐渐增加难度。",
                "media_url": "https://example.com/exercises/balance_training.mp4"
            }
        ],
        "physical_therapy": [
            {
                "name": "冰敷理疗",
                "frequency": "每日3次",
                "duration_minutes": 15,
                "description": "使用冰袋冷敷膝关节，减轻炎症和疼痛。"
            },
            {
                "name": "电刺激治疗",
                "frequency": "每周3次",
                "duration_minutes": 20,
                "description": "使用TENS设备进行电刺激，促进肌肉收缩和血液循环。"
            }
        ],
        "daily_activities": [
            "使用合适的支具或绷带保护膝关节",
            "避免剧烈运动和跳跃活动",
            "上下楼梯时使用扶手，减轻膝关节负担"
        ],
        "progress_metrics": [
            "疼痛评分(0-10)",
            "膝关节屈伸角度",
            "肌肉力量测试"
        ]
    },
    {
        "name": "脑卒中康复训练计划",
        "description": "针对脑卒中后遗症患者的综合康复计划，恢复运动功能和日常生活能力。",
        "duration_weeks": 16,
        "condition": "脑卒中后遗症",
        "exercises": [
            {
                "name": "坐位平衡训练",
                "frequency": "每日3次",
                "sets": 2,
                "reps": 10,
                "duration_minutes": 15,
                "description": "坐在稳定平面上，保持平衡，逐渐减少支撑。",
                "media_url": "https://example.com/exercises/sitting_balance.mp4"
            },
            {
                "name": "上肢功能训练",
                "frequency": "每日2次",
                "sets": 3,
                "reps": 12,
                "duration_minutes": 20,
                "description": "使用患侧上肢进行抓取、拿放和翻转物品的练习。",
                "media_url": "https://example.com/exercises/upper_limb_function.mp4"
            },
            {
                "name": "步态训练",
                "frequency": "每日1次",
                "sets": 1,
                "reps": 5,
                "duration_minutes": 20,
                "description": "在平行杠或辅助下进行步行训练，逐步减少辅助。",
                "media_url": "https://example.com/exercises/gait_training.mp4"
            }
        ],
        "physical_therapy": [
            {
                "name": "神经肌肉电刺激",
                "frequency": "每周5次",
                "duration_minutes": 30,
                "description": "使用电刺激设备促进肌肉收缩和神经重建。"
            },
            {
                "name": "镜像疗法",
                "frequency": "每日2次",
                "duration_minutes": 15,
                "description": "使用镜子创建健侧肢体的镜像，促进大脑重塑。"
            }
        ],
        "daily_activities": [
            "使用辅助设备进行日常活动，如特制餐具",
            "家庭环境改造，减少障碍物",
            "定时变换姿势，预防褥疮"
        ],
        "progress_metrics": [
            "Barthel指数评分",
            "运动功能评估",
            "平衡能力测试"
        ]
    }
]

async def create_test_rehab_plans():
    """创建测试康复计划数据"""
    print("开始创建测试康复计划数据...")
    
    # 连接数据库
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.MONGODB_DB_NAME]
    
    # 确保集合存在
    if "rehabilitation_plans" not in await db.list_collection_names():
        await db.create_collection("rehabilitation_plans")
    
    # 获取所有患者和医生
    patient_cursor = db.users.find({"role": "patient"})
    patients = []
    async for patient in patient_cursor:
        patients.append({"id": str(patient["_id"]), "name": patient.get("name", ""), "conditions": patient.get("medical_info", {}).get("main_diagnosis", "")})
    
    doctor_cursor = db.users.find({"role": "doctor"})
    doctors = []
    async for doctor in doctor_cursor:
        doctors.append({"id": str(doctor["_id"]), "name": doctor.get("name", "")})
    
    # 如果没有足够的患者或医生，则跳过创建
    if not patients or not doctors:
        print("没有足够的患者或医生数据，跳过康复计划创建。")
        client.close()
        return
    
    # 为每个患者创建1-2个康复计划
    for patient in patients:
        # 根据患者的主要诊断选择合适的康复计划模板
        suitable_templates = []
        for template in REHAB_PLAN_TEMPLATES:
            # 如果患者的诊断包含模板的适用条件，或者没有明确诊断，则添加该模板
            if not patient["conditions"] or patient["conditions"].find(template["condition"]) >= 0:
                suitable_templates.append(template)
        
        # 如果没有找到合适的模板，则随机选择
        if not suitable_templates:
            suitable_templates = REHAB_PLAN_TEMPLATES
        
        # 随机决定创建1-2个康复计划
        num_plans = random.randint(1, 2)
        for i in range(num_plans):
            # 随机选择一个模板和医生
            template = random.choice(suitable_templates)
            doctor = random.choice(doctors)
            
            # 生成计划开始和结束日期
            start_date = datetime.now() - timedelta(days=random.randint(0, 30))
            end_date = start_date + timedelta(weeks=template["duration_weeks"])
            
            # 生成随机的完成度
            progress_percentage = random.randint(0, 100)
            
            # 创建康复计划文档
            plan_doc = {
                "name": template["name"],
                "description": template["description"],
                "patient_id": patient["id"],
                "patient_name": patient["name"],
                "doctor_id": doctor["id"],
                "doctor_name": doctor["name"],
                "condition": template["condition"],
                "start_date": start_date,
                "end_date": end_date,
                "progress_percentage": progress_percentage,
                "status": "active" if end_date > datetime.now() else "completed",
                "exercises": template["exercises"],
                "physical_therapy": template["physical_therapy"],
                "daily_activities": template["daily_activities"],
                "progress_metrics": template["progress_metrics"],
                "created_at": datetime.now(),
                "updated_at": datetime.now()
            }
            
            # 插入文档
            result = await db.rehabilitation_plans.insert_one(plan_doc)
            
            # 更新患者的康复计划列表
            plan_id = str(result.inserted_id)
            await db.users.update_one(
                {"_id": ObjectId(patient["id"])},
                {"$addToSet": {"rehabilitation_plans": plan_id}}
            )
            
            print(f"为患者 {patient['name']} 创建康复计划: {template['name']} (ID: {plan_id})")
    
    # 关闭数据库连接
    client.close()
    print("测试康复计划数据创建完成！")

if __name__ == "__main__":
    asyncio.run(create_test_rehab_plans()) 