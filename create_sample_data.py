from motor.motor_asyncio import AsyncIOMotorClient
import asyncio
from datetime import datetime

async def create_sample_exercises():
    # 连接到MongoDB
    client = AsyncIOMotorClient('mongodb://localhost:27017')
    db = client.medical_assistant
    
    # 清空现有数据
    await db.exercises.delete_many({})
    
    # 示例数据
    exercises = [
        {
            'name': '肩部拉伸',
            'description': '改善肩关节活动范围的基础拉伸',
            'body_part': '肩部',
            'category': '拉伸',
            'difficulty': '简单',
            'duration_minutes': 5,
            'repetitions': 10,
            'sets': 2,
            'instructions': ['保持正确姿势', '缓慢进行动作', '不要过度拉伸'],
            'contraindications': ['急性肩伤'],
            'benefits': ['改善灵活性', '减轻肌肉紧张'],
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        },
        {
            'name': '膝关节强化',
            'description': '增强膝关节周围肌肉力量',
            'body_part': '膝关节',
            'category': '力量训练',
            'difficulty': '中等',
            'duration_minutes': 10,
            'repetitions': 12,
            'sets': 3,
            'instructions': ['使用适当重量', '控制动作速度', '注意膝关节角度'],
            'contraindications': ['急性膝伤'],
            'benefits': ['增强肌肉力量', '改善关节稳定性'],
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        },
        {
            'name': '腰背部稳定练习',
            'description': '增强腰背核心肌群稳定性',
            'body_part': '腰背',
            'category': '稳定性',
            'difficulty': '困难',
            'duration_minutes': 15,
            'repetitions': 8,
            'sets': 3,
            'instructions': ['保持中立脊柱', '缓慢控制动作', '专注腹肌收缩'],
            'contraindications': ['急性腰痛'],
            'benefits': ['增强核心稳定性', '预防腰痛'],
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
    ]
    
    # 插入数据
    result = await db.exercises.insert_many(exercises)
    print(f'已插入{len(result.inserted_ids)}条康复运动数据')

if __name__ == "__main__":
    asyncio.run(create_sample_exercises()) 