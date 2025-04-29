"""
健康档案服务测试
测试健康档案服务的各项功能
"""
import asyncio
import pytest
from datetime import datetime, timedelta
from bson import ObjectId

from app.services.health_record_service import HealthRecordService
from app.schemas.health_record import (
    HealthRecordCreate, HealthRecordUpdate,
    FollowUpRecordCreate, CompleteFollowUpRequest, CancelFollowUpRequest, RescheduleFollowUpRequest,
    HealthDataCreate
)

# 测试数据
TEST_PATIENT_ID = str(ObjectId())
TEST_DOCTOR_ID = str(ObjectId())
TEST_HEALTH_MANAGER_ID = str(ObjectId())


@pytest.mark.asyncio
async def test_create_health_record(db):
    """测试创建健康档案"""
    service = HealthRecordService(db)
    
    # 创建健康档案
    record_data = HealthRecordCreate(
        patient_id=TEST_PATIENT_ID,
        record_type="medical_record",
        title="测试门诊病历",
        content="这是一份测试的门诊病历内容",
        created_by=TEST_DOCTOR_ID
    )
    
    result = await service.create_health_record(record_data)
    
    # 验证结果
    assert result.id is not None
    assert result.patient_id == TEST_PATIENT_ID
    assert result.record_type == "medical_record"
    assert result.title == "测试门诊病历"
    assert result.created_by == TEST_DOCTOR_ID
    
    # 清理测试数据
    await db[service.health_records.name].delete_many({"patient_id": TEST_PATIENT_ID})
    await db[service.medical_timelines.name].delete_many({"patient_id": TEST_PATIENT_ID})


@pytest.mark.asyncio
async def test_update_health_record(db):
    """测试更新健康档案"""
    service = HealthRecordService(db)
    
    # 创建健康档案
    record_data = HealthRecordCreate(
        patient_id=TEST_PATIENT_ID,
        record_type="medical_record",
        title="测试门诊病历",
        content="这是一份测试的门诊病历内容",
        created_by=TEST_DOCTOR_ID
    )
    
    created_record = await service.create_health_record(record_data)
    
    # 更新健康档案
    update_data = HealthRecordUpdate(
        title="更新后的门诊病历",
        content="更新后的门诊病历内容",
        change_description="更新了标题和内容"
    )
    
    result = await service.update_health_record(
        record_id=created_record.id,
        record_data=update_data,
        updated_by=TEST_DOCTOR_ID
    )
    
    # 验证结果
    assert result.id == created_record.id
    assert result.title == "更新后的门诊病历"
    assert result.content == "更新后的门诊病历内容"
    assert result.current_version == 2  # 应该创建了新版本
    
    # 清理测试数据
    await db[service.health_records.name].delete_many({"patient_id": TEST_PATIENT_ID})
    await db[service.medical_timelines.name].delete_many({"patient_id": TEST_PATIENT_ID})


@pytest.mark.asyncio
async def test_create_followup_record(db):
    """测试创建随访记录"""
    service = HealthRecordService(db)
    
    # 创建随访记录
    followup_data = FollowUpRecordCreate(
        patient_id=TEST_PATIENT_ID,
        created_by=TEST_DOCTOR_ID,
        follow_up_type="phone",
        scheduled_date=datetime.utcnow() + timedelta(days=7),
        provider_id=TEST_DOCTOR_ID,
        description="测试电话随访"
    )
    
    result = await service.create_followup_record(followup_data)
    
    # 验证结果
    assert result.id is not None
    assert result.patient_id == TEST_PATIENT_ID
    assert result.follow_up_type == "phone"
    assert result.created_by == TEST_DOCTOR_ID
    assert result.status == "scheduled"
    
    # 清理测试数据
    await db[service.followup_records.name].delete_many({"patient_id": TEST_PATIENT_ID})
    await db[service.medical_timelines.name].delete_many({"patient_id": TEST_PATIENT_ID})


@pytest.mark.asyncio
async def test_complete_followup(db):
    """测试完成随访"""
    service = HealthRecordService(db)
    
    # 创建随访记录
    followup_data = FollowUpRecordCreate(
        patient_id=TEST_PATIENT_ID,
        created_by=TEST_DOCTOR_ID,
        follow_up_type="phone",
        scheduled_date=datetime.utcnow() + timedelta(days=7),
        provider_id=TEST_DOCTOR_ID,
        description="测试电话随访"
    )
    
    created_followup = await service.create_followup_record(followup_data)
    
    # 完成随访
    complete_data = CompleteFollowUpRequest(
        actual_date=datetime.utcnow(),
        answers=[],
        notes="患者恢复良好",
        follow_up_result="completed"
    )
    
    result = await service.complete_followup(created_followup.id, complete_data)
    
    # 验证结果
    assert result.id == created_followup.id
    assert result.status == "completed"
    assert result.actual_date is not None
    assert result.notes == "患者恢复良好"
    
    # 清理测试数据
    await db[service.followup_records.name].delete_many({"patient_id": TEST_PATIENT_ID})
    await db[service.medical_timelines.name].delete_many({"patient_id": TEST_PATIENT_ID})


@pytest.mark.asyncio
async def test_create_health_data(db):
    """测试创建健康数据"""
    service = HealthRecordService(db)
    
    # 创建健康数据
    data = HealthDataCreate(
        patient_id=TEST_PATIENT_ID,
        data_type="vital_sign",
        data_content={
            "type": "blood_pressure",
            "value": {"systolic": 120, "diastolic": 80},
            "unit": "mmHg"
        },
        recorded_by=TEST_PATIENT_ID
    )
    
    result = await service.create_health_data(data)
    
    # 验证结果
    assert result.id is not None
    assert result.patient_id == TEST_PATIENT_ID
    assert result.data_type == "vital_sign"
    assert result.data_content["type"] == "blood_pressure"
    assert result.data_content["value"]["systolic"] == 120
    
    # 清理测试数据
    await db[service.health_data.name].delete_many({"patient_id": TEST_PATIENT_ID})
    await db[service.medical_timelines.name].delete_many({"patient_id": TEST_PATIENT_ID})


@pytest.mark.asyncio
async def test_get_medical_timeline(db):
    """测试获取医疗时间线"""
    service = HealthRecordService(db)
    
    # 创建健康档案
    record_data = HealthRecordCreate(
        patient_id=TEST_PATIENT_ID,
        record_type="medical_record",
        title="测试门诊病历",
        content="这是一份测试的门诊病历内容",
        created_by=TEST_DOCTOR_ID
    )
    
    await service.create_health_record(record_data)
    
    # 创建随访记录
    followup_data = FollowUpRecordCreate(
        patient_id=TEST_PATIENT_ID,
        created_by=TEST_DOCTOR_ID,
        follow_up_type="phone",
        scheduled_date=datetime.utcnow() + timedelta(days=7),
        provider_id=TEST_DOCTOR_ID,
        description="测试电话随访"
    )
    
    await service.create_followup_record(followup_data)
    
    # 获取时间线
    timeline = await service.get_medical_timeline(TEST_PATIENT_ID)
    
    # 验证结果
    assert len(timeline) == 2
    assert timeline[0].patient_id == TEST_PATIENT_ID
    assert timeline[1].patient_id == TEST_PATIENT_ID
    
    # 清理测试数据
    await db[service.health_records.name].delete_many({"patient_id": TEST_PATIENT_ID})
    await db[service.followup_records.name].delete_many({"patient_id": TEST_PATIENT_ID})
    await db[service.medical_timelines.name].delete_many({"patient_id": TEST_PATIENT_ID})


if __name__ == "__main__":
    # 直接运行测试
    loop = asyncio.get_event_loop()
    from app.db.mongodb import get_database
    from app.core.config import settings
    
    async def main():
        # 连接测试数据库
        from motor.motor_asyncio import AsyncIOMotorClient
        client = AsyncIOMotorClient(settings.MONGODB_URL)
        db = client[settings.MONGODB_DB + "_test"]
        
        # 运行测试
        await test_create_health_record(db)
        print("✅ 创建健康档案测试通过")
        
        await test_update_health_record(db)
        print("✅ 更新健康档案测试通过")
        
        await test_create_followup_record(db)
        print("✅ 创建随访记录测试通过")
        
        await test_complete_followup(db)
        print("✅ 完成随访测试通过")
        
        await test_create_health_data(db)
        print("✅ 创建健康数据测试通过")
        
        await test_get_medical_timeline(db)
        print("✅ 获取医疗时间线测试通过")
        
        # 关闭连接
        client.close()
    
    loop.run_until_complete(main()) 