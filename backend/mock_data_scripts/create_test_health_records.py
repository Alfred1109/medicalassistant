"""
测试健康记录数据生成脚本
用于向MongoDB数据库添加模拟健康记录数据
"""
import asyncio
import random
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings
from datetime import datetime, timedelta
from bson import ObjectId

# 模拟健康记录模板
HEALTH_RECORD_TEMPLATES = [
    {
        "title": "骨科康复评估记录",
        "content": {
            "chief_complaint": "患者主诉腰部疼痛，活动受限，疼痛持续时间约3个月，休息后稍有缓解。",
            "history_present_illness": "患者3个月前因搬重物后出现腰痛，未经正规治疗，症状逐渐加重。",
            "physical_examination": {
                "general": "一般情况良好，神志清楚，精神状态正常",
                "vital_signs": {
                    "blood_pressure": "130/85 mmHg",
                    "heart_rate": "78 bpm",
                    "respiratory_rate": "18 bpm",
                    "temperature": "36.5 °C"
                },
                "spine": "腰椎活动度受限，前屈不超过60度，腰椎旁肌肉有压痛，无放射痛",
                "neurological": "双下肢肌力和感觉正常，膝腱反射和踝腱反射正常",
                "straight_leg_raise": "阴性"
            },
            "diagnosis": "腰椎间盘突出症",
            "treatment_plan": {
                "medications": [
                    {
                        "name": "布洛芬缓释胶囊",
                        "dosage": "300mg",
                        "frequency": "bid",
                        "duration": "7天"
                    },
                    {
                        "name": "甲钴胺片",
                        "dosage": "0.5mg",
                        "frequency": "tid",
                        "duration": "30天"
                    }
                ],
                "physical_therapy": [
                    "腰椎牵引 20分钟/次 每日1次",
                    "腰部热疗 15分钟/次 每日2次",
                    "腰背肌功能锻炼 每日3次"
                ],
                "lifestyle_modifications": [
                    "避免长时间坐立",
                    "保持正确坐姿和站姿",
                    "避免提重物"
                ],
                "follow_up": "2周后复诊"
            }
        },
        "tags": ["骨科", "腰椎", "疼痛"]
    },
    {
        "title": "神经康复评估记录",
        "content": {
            "chief_complaint": "患者主诉左侧肢体活动不灵活，左侧面部轻度麻木，语言表达困难。",
            "history_present_illness": "患者1个月前突发左侧肢体无力、言语不清，被诊断为脑梗塞，经急性期治疗后转入康复科。",
            "physical_examination": {
                "general": "精神状态尚可，神志清楚，有构音障碍",
                "vital_signs": {
                    "blood_pressure": "145/90 mmHg",
                    "heart_rate": "82 bpm",
                    "respiratory_rate": "20 bpm",
                    "temperature": "36.7 °C"
                },
                "neurological": {
                    "consciousness": "清醒",
                    "orientation": "完全定向",
                    "speech": "构音障碍，理解正常",
                    "cranial_nerves": "左侧面部感觉减退，左侧鼻唇沟变浅",
                    "motor": "左上肢肌力3级，左下肢肌力4级",
                    "sensory": "左侧肢体感觉减退",
                    "coordination": "左侧指鼻试验不准确",
                    "reflexes": "左侧肌腱反射亢进，巴宾斯基征阳性"
                }
            },
            "diagnosis": "脑梗塞后遗症，左侧偏瘫",
            "treatment_plan": {
                "medications": [
                    {
                        "name": "阿司匹林肠溶片",
                        "dosage": "100mg",
                        "frequency": "qd",
                        "duration": "长期"
                    },
                    {
                        "name": "阿托伐他汀钙片",
                        "dosage": "20mg",
                        "frequency": "qn",
                        "duration": "长期"
                    }
                ],
                "rehabilitation": [
                    "运动疗法：肢体主动运动训练、平衡训练 每日2次",
                    "作业疗法：日常生活活动训练 每日1次",
                    "言语训练 每日1次"
                ],
                "follow_up": "2周后复诊",
                "lifestyle_modifications": [
                    "控制血压",
                    "低盐低脂饮食",
                    "适当运动"
                ]
            }
        },
        "tags": ["神经内科", "脑卒中", "偏瘫", "康复"]
    },
    {
        "title": "心脏康复评估记录",
        "content": {
            "chief_complaint": "患者主诉活动后胸闷、气短，轻度活动耐力下降。",
            "history_present_illness": "患者2个月前因急性心肌梗死入院，行冠状动脉支架植入术，现处于恢复期。",
            "physical_examination": {
                "general": "一般情况尚可，精神状态良好",
                "vital_signs": {
                    "blood_pressure": "125/75 mmHg",
                    "heart_rate": "68 bpm",
                    "respiratory_rate": "16 bpm",
                    "temperature": "36.4 °C"
                },
                "cardiovascular": {
                    "heart_sounds": "心律规则，无杂音",
                    "peripheral_pulses": "双侧桡动脉搏动对称",
                    "jugular_venous_pressure": "正常",
                    "edema": "无下肢水肿"
                },
                "respiratory": "呼吸音清晰，无啰音",
                "six_minute_walk_test": "距离450米，轻度气促"
            },
            "diagnosis": "冠心病，心肌梗死后状态",
            "treatment_plan": {
                "medications": [
                    {
                        "name": "阿司匹林肠溶片",
                        "dosage": "100mg",
                        "frequency": "qd",
                        "duration": "长期"
                    },
                    {
                        "name": "氯吡格雷片",
                        "dosage": "75mg",
                        "frequency": "qd",
                        "duration": "12个月"
                    },
                    {
                        "name": "美托洛尔缓释片",
                        "dosage": "47.5mg",
                        "frequency": "qd",
                        "duration": "长期"
                    }
                ],
                "cardiac_rehabilitation": [
                    "有氧运动训练 每周5次 每次30分钟",
                    "渐进性阻抗训练 每周3次",
                    "心理支持与健康教育"
                ],
                "lifestyle_modifications": [
                    "戒烟限酒",
                    "低盐低脂饮食",
                    "体重管理",
                    "压力管理"
                ],
                "follow_up": "1个月后复诊"
            }
        },
        "tags": ["心脏科", "冠心病", "心肌梗死", "康复"]
    }
]

# 模拟随访记录模板
FOLLOW_UP_TEMPLATES = [
    {
        "title": "骨科康复随访记录",
        "content": {
            "subjective": "患者反映腰痛有所缓解，但活动后仍有轻度不适。",
            "objective": {
                "vital_signs": {
                    "blood_pressure": "125/80 mmHg",
                    "heart_rate": "72 bpm"
                },
                "physical_examination": "腰椎活动度改善，前屈可达80度，腰椎旁压痛减轻"
            },
            "assessment": "腰椎间盘突出症，恢复良好",
            "plan": {
                "continue_medications": [
                    {
                        "name": "甲钴胺片",
                        "dosage": "0.5mg",
                        "frequency": "tid",
                        "duration": "30天"
                    }
                ],
                "adjust_therapy": "增加核心肌群训练，每日2次",
                "next_follow_up": "1个月后复诊"
            }
        }
    },
    {
        "title": "神经康复随访记录",
        "content": {
            "subjective": "患者反映左侧肢体力量有所恢复，日常生活活动能力提高。",
            "objective": {
                "vital_signs": {
                    "blood_pressure": "138/85 mmHg",
                    "heart_rate": "76 bpm"
                },
                "neurological_exam": {
                    "motor": "左上肢肌力提高至4级，左下肢肌力4+级",
                    "coordination": "左侧指鼻试验准确性提高"
                },
                "functional_assessment": "Barthel指数从45分提高至65分"
            },
            "assessment": "脑梗塞后遗症，恢复进展良好",
            "plan": {
                "continue_medications": "维持原有药物治疗",
                "adjust_therapy": "加强平衡训练和精细动作训练",
                "next_follow_up": "2周后复诊"
            }
        }
    },
    {
        "title": "心脏康复随访记录",
        "content": {
            "subjective": "患者反映活动耐力有所提高，偶有轻度胸闷。",
            "objective": {
                "vital_signs": {
                    "blood_pressure": "120/75 mmHg",
                    "heart_rate": "65 bpm"
                },
                "cardiovascular_exam": "心律规则，无杂音",
                "six_minute_walk_test": "距离增加至500米，无明显气促"
            },
            "assessment": "冠心病，心肌梗死后状态，康复进展良好",
            "plan": {
                "continue_medications": "维持原有药物治疗",
                "adjust_therapy": "增加有氧运动强度，达到心率储备的60-70%",
                "next_follow_up": "2个月后复诊"
            }
        }
    }
]

async def create_test_health_records():
    """创建测试健康记录数据"""
    print("开始创建测试健康记录数据...")
    
    # 连接数据库
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.MONGODB_DB_NAME]
    
    # 确保健康记录集合存在
    if "health_records" not in await db.list_collection_names():
        await db.create_collection("health_records")
    
    # 确保随访记录集合存在
    if "follow_ups" not in await db.list_collection_names():
        await db.create_collection("follow_ups")
    
    # 获取所有患者和医生
    patient_cursor = db.users.find({"role": "patient"})
    patients = []
    async for patient in patient_cursor:
        patients.append({
            "id": str(patient["_id"]),
            "name": patient.get("name", ""),
            "conditions": patient.get("medical_info", {}).get("main_diagnosis", "")
        })
    
    doctor_cursor = db.users.find({"role": "doctor"})
    doctors = []
    async for doctor in doctor_cursor:
        doctors.append({
            "id": str(doctor["_id"]),
            "name": doctor.get("name", ""),
            "specialty": doctor.get("specialty", "")
        })
    
    # 如果没有足够的患者或医生，则跳过创建
    if not patients or not doctors:
        print("没有足够的患者或医生数据，跳过健康记录创建。")
        client.close()
        return
    
    # 为每个患者创建1-3个健康记录
    for patient in patients:
        # 根据患者的主要诊断选择合适的健康记录模板
        suitable_templates = []
        
        for template in HEALTH_RECORD_TEMPLATES:
            # 如果患者的诊断包含模板的标签内容，或者没有明确诊断，则添加该模板
            if not patient["conditions"] or any(tag in patient["conditions"] for tag in template["tags"]):
                suitable_templates.append(template)
        
        # 如果没有找到合适的模板，则使用所有模板
        if not suitable_templates:
            suitable_templates = HEALTH_RECORD_TEMPLATES
        
        # 随机决定创建1-3个健康记录
        num_records = random.randint(1, 3)
        for i in range(num_records):
            # 随机选择一个模板和医生
            template = random.choice(suitable_templates)
            
            # 选择专业匹配的医生，如果没有则随机选择
            matching_doctors = [d for d in doctors if any(tag in d.get("specialty", "") for tag in template["tags"])]
            doctor = random.choice(matching_doctors) if matching_doctors else random.choice(doctors)
            
            # 生成记录创建日期（过去1-60天内）
            created_at = datetime.now() - timedelta(days=random.randint(1, 60))
            
            # 创建健康记录文档
            record_doc = {
                "title": template["title"],
                "content": template["content"],
                "patient_id": patient["id"],
                "patient_name": patient["name"],
                "doctor_id": doctor["id"],
                "doctor_name": doctor["name"],
                "tags": template["tags"],
                "status": "active",
                "version": 1,
                "created_at": created_at,
                "updated_at": created_at
            }
            
            # 插入文档
            result = await db.health_records.insert_one(record_doc)
            record_id = str(result.inserted_id)
            
            print(f"为患者 {patient['name']} 创建健康记录: {template['title']} (ID: {record_id})")
            
            # 50%的概率创建随访记录
            if random.random() < 0.5:
                # 随机选择一个随访模板
                follow_up_template = random.choice(FOLLOW_UP_TEMPLATES)
                
                # 随访日期设置为记录创建后5-30天
                follow_up_date = created_at + timedelta(days=random.randint(5, 30))
                
                # 随访状态
                status = "completed" if follow_up_date < datetime.now() else "scheduled"
                
                # 创建随访记录
                follow_up_doc = {
                    "title": follow_up_template["title"],
                    "content": follow_up_template["content"] if status == "completed" else {},
                    "patient_id": patient["id"],
                    "patient_name": patient["name"],
                    "doctor_id": doctor["id"],
                    "doctor_name": doctor["name"],
                    "health_record_id": record_id,
                    "scheduled_date": follow_up_date,
                    "completed_date": follow_up_date if status == "completed" else None,
                    "status": status,
                    "created_at": created_at,
                    "updated_at": follow_up_date if status == "completed" else created_at
                }
                
                # 插入随访记录
                result = await db.follow_ups.insert_one(follow_up_doc)
                follow_up_id = str(result.inserted_id)
                
                print(f"  - 为健康记录创建随访: {follow_up_template['title']} (ID: {follow_up_id})")
    
    # 关闭数据库连接
    client.close()
    print("测试健康记录数据创建完成！")

if __name__ == "__main__":
    asyncio.run(create_test_health_records()) 