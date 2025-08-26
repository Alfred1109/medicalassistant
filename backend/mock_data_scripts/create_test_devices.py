"""
测试设备数据生成脚本
用于向MongoDB数据库添加模拟康复设备数据
"""
import asyncio
import random
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings
from datetime import datetime, timedelta
from bson import ObjectId

# 模拟设备数据
MOCK_DEVICES = [
    {
        "name": "智能手环-A1",
        "type": "wearable",
        "model": "HealthBand-Pro",
        "manufacturer": "健康科技",
        "description": "高精度运动追踪智能手环，支持心率、血氧和活动监测",
        "capabilities": ["heart_rate", "blood_oxygen", "steps", "sleep", "activity"],
        "connectivity": ["bluetooth", "wifi"],
        "battery_life_hours": 168,  # 7天
        "data_metrics": [
            {
                "name": "heart_rate",
                "unit": "bpm",
                "min_value": 40,
                "max_value": 220,
                "sampling_frequency": "continuous"
            },
            {
                "name": "blood_oxygen",
                "unit": "%",
                "min_value": 80,
                "max_value": 100,
                "sampling_frequency": "every_30_min"
            },
            {
                "name": "steps",
                "unit": "count",
                "min_value": 0,
                "max_value": 100000,
                "sampling_frequency": "continuous"
            },
            {
                "name": "sleep",
                "unit": "stage",
                "min_value": 0,
                "max_value": 4,
                "sampling_frequency": "every_5_min"
            }
        ],
        "status": "active"
    },
    {
        "name": "康复腕力器-KF200",
        "type": "rehabilitation",
        "model": "RehabGrip-200",
        "manufacturer": "康复器械有限公司",
        "description": "智能腕力康复训练器，可连接App记录训练数据和进度",
        "capabilities": ["grip_strength", "training_time", "repetitions"],
        "connectivity": ["bluetooth"],
        "battery_life_hours": 48,
        "data_metrics": [
            {
                "name": "grip_strength",
                "unit": "kg",
                "min_value": 0,
                "max_value": 100,
                "sampling_frequency": "per_exercise"
            },
            {
                "name": "repetitions",
                "unit": "count",
                "min_value": 0,
                "max_value": 1000,
                "sampling_frequency": "per_exercise"
            },
            {
                "name": "training_time",
                "unit": "seconds",
                "min_value": 0,
                "max_value": 7200,
                "sampling_frequency": "per_exercise"
            }
        ],
        "status": "active"
    },
    {
        "name": "步态分析系统-G500",
        "type": "diagnostic",
        "model": "GaitAnalyzer-500",
        "manufacturer": "医疗设备集团",
        "description": "高精度步态分析系统，用于评估患者步行模式和康复进展",
        "capabilities": ["gait_analysis", "balance_assessment", "weight_distribution"],
        "connectivity": ["usb", "wifi"],
        "battery_life_hours": 8,
        "data_metrics": [
            {
                "name": "stride_length",
                "unit": "cm",
                "min_value": 0,
                "max_value": 200,
                "sampling_frequency": "per_step"
            },
            {
                "name": "cadence",
                "unit": "steps/min",
                "min_value": 0,
                "max_value": 200,
                "sampling_frequency": "per_session"
            },
            {
                "name": "weight_distribution",
                "unit": "%",
                "min_value": 0,
                "max_value": 100,
                "sampling_frequency": "per_step"
            }
        ],
        "status": "active"
    },
    {
        "name": "智能血压计-BP100",
        "type": "monitoring",
        "model": "SmartBP-100",
        "manufacturer": "健康科技",
        "description": "智能蓝牙血压计，自动记录测量数据并同步至App",
        "capabilities": ["blood_pressure", "heart_rate"],
        "connectivity": ["bluetooth"],
        "battery_life_hours": 720,  # 30天
        "data_metrics": [
            {
                "name": "systolic",
                "unit": "mmHg",
                "min_value": 60,
                "max_value": 250,
                "sampling_frequency": "per_measurement"
            },
            {
                "name": "diastolic",
                "unit": "mmHg",
                "min_value": 40,
                "max_value": 150,
                "sampling_frequency": "per_measurement"
            },
            {
                "name": "heart_rate",
                "unit": "bpm",
                "min_value": 40,
                "max_value": 200,
                "sampling_frequency": "per_measurement"
            }
        ],
        "status": "active"
    }
]

# 模拟设备数据生成函数
async def generate_mock_device_data(device_type, metrics, days=30):
    """为特定设备类型生成模拟数据"""
    data_points = []
    
    # 确定每天生成的数据点数量
    if device_type == "wearable":
        points_per_day = 24  # 每小时1个数据点
    elif device_type == "rehabilitation":
        points_per_day = random.randint(1, 3)  # 每天1-3次训练
    elif device_type == "diagnostic":
        points_per_day = random.randint(0, 1)  # 偶尔进行诊断
    elif device_type == "monitoring":
        points_per_day = random.randint(1, 3)  # 每天1-3次测量
    else:
        points_per_day = 1
    
    # 生成过去days天的数据
    for day in range(days, 0, -1):
        date = datetime.now() - timedelta(days=day)
        
        # 对每天生成指定数量的数据点
        for i in range(points_per_day):
            # 设置时间
            hour = random.randint(8, 20)  # 假设数据在白天8点到晚上8点之间生成
            minute = random.randint(0, 59)
            second = random.randint(0, 59)
            timestamp = date.replace(hour=hour, minute=minute, second=second)
            
            # 为每个指标生成随机值
            metric_values = {}
            for metric in metrics:
                min_val = metric["min_value"]
                max_val = metric["max_value"]
                
                # 对于一些指标，生成具有逻辑性的数据
                if metric["name"] == "heart_rate":
                    # 心率在运动后升高
                    if random.random() < 0.3:  # 30%的概率表示运动状态
                        value = random.randint(100, 150)
                    else:
                        value = random.randint(60, 100)
                elif metric["name"] == "blood_oxygen":
                    # 血氧在正常范围内小幅波动
                    value = random.randint(95, 100)
                elif metric["name"] == "steps":
                    # 步数在一天内累积
                    value = random.randint(500, 2000) * (i + 1) // points_per_day
                elif metric["name"] in ["grip_strength", "repetitions", "training_time"]:
                    # 康复训练数据随时间改善
                    improvement_factor = min(1.5, 1 + 0.5 * (days - day) / days)
                    base_value = random.randint(min_val, (min_val + max_val) // 2)
                    value = int(base_value * improvement_factor)
                else:
                    value = random.randint(min_val, max_val)
                
                metric_values[metric["name"]] = value
            
            # 创建数据点
            data_point = {
                "timestamp": timestamp,
                "values": metric_values
            }
            
            data_points.append(data_point)
    
    return data_points

async def create_test_devices():
    """创建测试设备数据"""
    print("开始创建测试设备数据...")
    
    # 连接数据库
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.MONGODB_DB_NAME]
    
    # 确保设备集合存在
    if "devices" not in await db.list_collection_names():
        await db.create_collection("devices")
    
    # 确保设备数据集合存在
    if "device_data" not in await db.list_collection_names():
        await db.create_collection("device_data")
    
    # 获取所有患者
    patient_cursor = db.users.find({"role": "patient"})
    patients = []
    async for patient in patient_cursor:
        patients.append({"id": str(patient["_id"]), "name": patient.get("name", "")})
    
    # 如果没有患者，则跳过创建
    if not patients:
        print("没有患者数据，跳过设备创建。")
        client.close()
        return
    
    # 为每种设备类型创建实例
    for device_template in MOCK_DEVICES:
        # 为每个设备生成唯一的序列号
        serial_number = f"SN-{device_template['model']}-{random.randint(10000, 99999)}"
        
        # 随机选择一个患者
        patient = random.choice(patients)
        
        # 创建设备文档
        device_doc = {
            "name": device_template["name"],
            "type": device_template["type"],
            "model": device_template["model"],
            "manufacturer": device_template["manufacturer"],
            "serial_number": serial_number,
            "description": device_template["description"],
            "capabilities": device_template["capabilities"],
            "connectivity": device_template["connectivity"],
            "battery_life_hours": device_template["battery_life_hours"],
            "data_metrics": device_template["data_metrics"],
            "status": device_template["status"],
            "patient_id": patient["id"],
            "patient_name": patient["name"],
            "last_sync": datetime.now() - timedelta(days=random.randint(0, 3)),
            "created_at": datetime.now() - timedelta(days=random.randint(30, 60)),
            "updated_at": datetime.now()
        }
        
        # 插入设备文档
        result = await db.devices.insert_one(device_doc)
        device_id = str(result.inserted_id)
        
        # 更新患者的设备列表
        await db.users.update_one(
            {"_id": ObjectId(patient["id"])},
            {"$addToSet": {"devices": device_id}}
        )
        
        print(f"已创建设备: {device_template['name']} (ID: {device_id}) 分配给患者: {patient['name']}")
        
        # 生成设备历史数据
        device_data = await generate_mock_device_data(
            device_template["type"],
            device_template["data_metrics"]
        )
        
        # 如果有数据，插入数据库
        if device_data:
            # 为每个数据点添加设备ID
            for data_point in device_data:
                data_point["device_id"] = device_id
                data_point["created_at"] = datetime.now()
            
            # 批量插入数据
            await db.device_data.insert_many(device_data)
            print(f"  - 已为设备生成 {len(device_data)} 条历史数据")
    
    # 关闭数据库连接
    client.close()
    print("测试设备数据创建完成！")

if __name__ == "__main__":
    asyncio.run(create_test_devices()) 