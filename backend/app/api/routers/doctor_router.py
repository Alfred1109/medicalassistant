from fastapi import APIRouter, Depends, HTTPException, Query, status
from typing import Any, Dict, List, Optional
from datetime import datetime
import json
from app.schemas.user import UserResponse
from app.schemas.followup import FollowUpRecordCreate, FollowUpRecordResponse, FollowUpStatus
from app.api.dependencies import get_current_user, get_database, format_mongo_doc, get_health_record_for_patient, get_followup_service
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.db.crud_services import PatientCRUD
from app.models.user import Patient
from app.core.patient_access import assigned_scope_ids, ensure_patient_access, PatientAccessError
from app.core.exceptions import AppBaseException
from app.services.followup_service import FollowupService
from app.core.followup_access import ensure_followup_patient_access, followup_patient_scope
from bson.objectid import ObjectId

router = APIRouter()


def _emergency_contact(value):
    if isinstance(value, str):
        return value or "未设置"
    if isinstance(value, dict) and value:
        return json.dumps(value, ensure_ascii=False, default=str)
    return "未设置"


async def load_provider_health_record(db, patient_id, operator_id, role):
    """医护查看一名归属患者的健康档案。医生与健康管理师共用这一份读取。"""
    patient = await ensure_patient_access(db, patient_id, str(operator_id), role)
    record = await get_health_record_for_patient(patient_id, db)
    cursor = db["health_data"].find({"patient_id": patient_id, "data_type": "vital_sign", "deleted": {"$ne": True}})
    facts = await cursor.sort("recorded_at", -1).limit(100).to_list(length=100)
    vital_signs = [format_mongo_doc(fact) for fact in facts]
    if not record:
        return {
            "id": patient_id,
            "name": patient.get("name", "未知患者"),
            "age": patient.get("age", 0),
            "gender": patient.get("gender", "未知"),
            "height": patient.get("height", 0),
            "weight": patient.get("weight", 0),
            "bloodType": patient.get("blood_type", "未知"),
            "allergies": patient.get("allergies", []),
            "emergencyContact": _emergency_contact(patient.get("emergency_contact")),
            "medicalHistory": [],
            "rehabHistory": [],
            "medications": [],
            "vitalSigns": vital_signs
        }
    return {
        "id": record.get("id") or record.get("_id") or patient_id,
        "name": record.get("name", patient.get("name", "未知患者")),
        "age": record.get("age", 0),
        "gender": record.get("gender", "未知"),
        "height": record.get("height", 0),
        "weight": record.get("weight", 0),
        "bloodType": record.get("blood_type", "未知"),
        "allergies": record.get("allergies", []),
        "emergencyContact": _emergency_contact(record.get("emergency_contact", patient.get("emergency_contact"))),
        "medicalHistory": record.get("medical_history", []),
        "rehabHistory": record.get("rehab_history", []),
        "medications": record.get("medications", []),
        "vitalSigns": vital_signs
    }


async def load_provider_monitoring(db, patient_id, operator_id, role):
    """医护查看一名归属患者的监测快照。无数据时计数为 0。"""
    if not ObjectId.is_valid(patient_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到患者信息")
    await ensure_patient_access(db, patient_id, str(operator_id), role)
    plans_collection = db["rehab_plans"]
    total_plans = await plans_collection.count_documents({"patient_id": patient_id})
    active_plans = await plans_collection.count_documents(
        {"patient_id": patient_id, "status": "active"})
    completed_plans = await plans_collection.count_documents(
        {"patient_id": patient_id, "status": "completed"})
    return {
        "implemented": True,
        "patientId": patient_id,
        "boundDevices": await db["devices"].count_documents({"patient_id": patient_id}),
        "rehabPlans": {
            "total": total_plans,
            "active": active_plans,
            "completed": completed_plans,
        },
    }


# 医生功能路由

# 患者管理
@router.get("/patients", response_model=List[dict])
async def get_doctor_patients(
    skip: int = Query(0, description="分页偏移量，缺省 0（不翻页）"),
    limit: Optional[int] = Query(
        None, description="每页数量（1-200）；缺省不传=一次性全量（legacy）"
                          "/canonical 域默认前 100 条按 patient_id 排序"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """获取医生管理的患者列表

    T59 分页预适配：skip/limit 为可选参数，缺省（不传）与既有一次性全量
    行为完全一致。显式分页时两域执行同一约束（skip≥0、1≤limit≤200），
    越界返回 503 INVALID_PATIENT_PAGINATION（校验在服务层统一执行，
    不在 Query 层拦截，保证错误码与 canonical 仓库语义一致）。
    """
    if current_user.role != "doctor":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")

    # 从数据库获取患者数据
    patient_crud = PatientCRUD(db, Patient)

    try:
        # 获取当前医生的所有患者
        doctor_id = current_user.id
        patients_data = await patient_crud.find_by_doctor_id(
            doctor_id, skip=skip, limit=limit)
    except AppBaseException:
        # 适配器的患者标识歧义（PATIENT_IDENTITY_AMBIGUOUS/503）等业务异常
        # 保留全局处理器语义，不降级为 500
        raise
    except Exception as e:
        # 记录错误并如实上抛为 500，绝不返回模拟患者
        print(f"获取患者数据时出错: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取患者列表失败，请稍后重试"
        )

    # 空库/该医生暂无关联患者：如实返回空列表（不再返回 mock_i 模拟数据）
    return patients_data

# 健康档案
@router.get("/health-records/{patient_id}", response_model=dict)
async def get_patient_health_record(
    patient_id: str, 
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """获取患者健康档案"""
    if current_user.role != "doctor":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    
    try:
        return await load_provider_health_record(
            db, patient_id, current_user.id, current_user.role)
    except (HTTPException, PatientAccessError):
        raise
    except Exception as e:
        print(f"获取患者健康档案时出错: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取健康档案失败，请稍后重试"
        )

# 随访管理
# FU01 S2 收敛：/api/doctors/follow-ups 与唯一正典入口 /api/health-records/followups
# 同源（FollowupService）同形状（FollowUpRecordResponse 响应契约），
# 删除路由层直连 followup_records 集合与 new_follow_up_id 假 ID 逻辑
@router.get("/follow-ups", response_model=List[FollowUpRecordResponse])
async def get_follow_ups(
    followup_status: Optional[str] = Query(None, alias="status"),
    current_user: UserResponse = Depends(get_current_user),
    followup_service: FollowupService = Depends(get_followup_service)
):
    """获取当前医生的随访列表（转调 FollowupService，同源同形状）"""
    if current_user.role != "doctor":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")

    try:
        scope = await followup_patient_scope(followup_service.db, current_user)
        return await followup_service.list_followups_for_provider(
            current_user.id, status=followup_status, patient_ids=scope)
    except Exception as e:
        print(f"获取随访列表时出错: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取随访列表失败，请稍后重试"
        )

@router.post("/follow-ups", status_code=status.HTTP_201_CREATED, response_model=FollowUpRecordResponse)
async def create_follow_up(
    follow_up_data: FollowUpRecordCreate,
    current_user: UserResponse = Depends(get_current_user),
    followup_service: FollowupService = Depends(get_followup_service)
):
    """创建随访计划（转调 FollowupService，返回真实记录 ID 与响应契约）"""
    if current_user.role != "doctor":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    # 创建人缺省为当前医生（与 canonical 创建端点一致；provider_id 为必填契约字段）
    await ensure_followup_patient_access(followup_service.db, follow_up_data.patient_id, current_user, write=True)
    follow_up_data.created_by = current_user.id
    return await followup_service.create_followup_record(follow_up_data)

# 数据监测
@router.get("/patient-monitoring/{patient_id}", response_model=dict)
async def get_patient_monitoring_data(
    patient_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """获取患者监测数据（真实聚合快照，2026-11-08 替换存根空对象）

    字段语义（均来自真实集合，无数据时如实为 0）：
    - boundDevices:  绑定到该患者的设备数（devices.patient_id）
    - rehabPlans:    该患者的康复计划总数/进行中/已完成（rehab_plans.patient_id）
    - implemented:   显式标记端点已实现真实聚合
    - start_date/end_date 参数为历史签名保留，当前快照类指标不按时间切片
    """
    if current_user.role != "doctor":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    try:
        return await load_provider_monitoring(
            db, patient_id, current_user.id, current_user.role)
    except (HTTPException, PatientAccessError):
        raise
    except Exception as e:
        print(f"获取患者监测数据时出错: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取患者监测数据失败，请稍后重试"
        )

# 随访「待完成」状态：未终结、仍需医护跟进的状态集合。
# 医患消息走 /api/communications，这里不再保留返回空列表或假 ID 的存根。
# completed / canceled / lost 属终态（已完成 / 已取消 / 失访认定），不计入待完成。
FOLLOW_UP_PENDING_STATUSES = (
    FollowUpStatus.PENDING_SCHEDULE.value,
    FollowUpStatus.SCHEDULED.value,
    FollowUpStatus.AWAITING_FILL.value,
    FollowUpStatus.IN_REVIEW.value,
    FollowUpStatus.MISSED.value,
    FollowUpStatus.OVERDUE.value,
    FollowUpStatus.RESCHEDULED.value,
)


async def collect_follow_up_statistics(
    followup_service: FollowupService, patient_ids: List[str]
) -> Dict[str, int]:
    """随访统计（唯一入口 FollowupService；路由层不直连 followup_records 集合）。

    口径与 FollowupService.list_all_followups 同源：排除已删除节点、患者
    范围由调用方传入。分页拉取以免一次性载入全部随访记录。
    """
    pending_statuses = set(FOLLOW_UP_PENDING_STATUSES)
    total = completed = pending = 0
    skip = 0
    page_size = 200
    while True:
        records = await followup_service.list_all_followups(
            skip=skip, limit=page_size, patient_ids=patient_ids)
        if not records:
            break
        for record in records:
            total += 1
            status = getattr(record, "status", None)
            status_value = getattr(status, "value", status)
            if status_value == FollowUpStatus.COMPLETED.value:
                completed += 1
            elif status_value in pending_statuses:
                pending += 1
        skip += len(records)
        if len(records) < page_size:
            break
    return {"total": total, "completed": completed, "pending": pending}


async def collect_work_statistics(
    db: AsyncIOMotorDatabase,
    *,
    operator_id: str,
    operator_role: str,
    plan_scope: str,
    operator_label: str,
    followup_service: Optional[FollowupService] = None,
) -> Dict[str, Any]:
    """医护工作统计的唯一聚合实现（医生与健康管理师共用，避免第三份复制）。

    归属判定统一走 app.core.patient_access.assigned_scope_ids（域感知：
    legacy 执行于 users、canonical 执行于 clinical_patients，含标识歧义
    防护 PATIENT_IDENTITY_AMBIGUOUS），本函数不自写归属规则。

    plan_scope —— 康复方案的归属口径（两个角色确实不同，各自说明）：
    - "owner"：按 practitioner_id 归属本人。医生既有口径（rehab_plans 的
      写入方只写 practitioner_id），保持既有契约不变。
    - "patients"：按本人归属患者范围。rehab_plans 的 health_manager_id
      字段从未有写入方（模型字段从未落库），按该字段统计将恒为 0 而非真实；
      健康管理师采用此口径，与 GET /rehabilitation/plans 的授权范围一致。

    followup_service —— 传入时附带随访统计（健康管理师端开启；医生端既有
    响应契约不含随访字段，保持不变）。随访集合只经 FollowupService 读取。

    返回值均来自真实集合，无数据时如实为 0：
    patientCount / rehabPlans{total,active,completed} /
    patientSelfReportsThisMonth{total,completed,partial,not_done} /
    （可选）followUps{total,completed,pending}。患者自报按 performed_at 统计，
    只表示自报条数，不代表已核验训练场次或依从性。
    """
    operator = await db["users"].find_one(
        {"_id": ObjectId(str(operator_id)), "role": operator_role})
    if not operator:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"未找到{operator_label}信息")

    # 患者范围：域感知的归属解析（legacy 双字面归属 + 标识歧义防护）
    patient_ids = await assigned_scope_ids(db, str(operator_id), operator_role)
    patient_keys = [str(patient_id) for patient_id in patient_ids]

    if plan_scope == "owner":
        plan_filter: Dict[str, Any] = {"practitioner_id": str(operator_id)}
    elif plan_scope == "patients":
        plan_filter = {"patient_id": {"$in": patient_keys}}
    else:
        raise ValueError(f"未知的康复方案归属口径: {plan_scope}")
    plans_collection = db["rehab_plans"]
    total_plans = await plans_collection.count_documents(plan_filter)
    active_plans = await plans_collection.count_documents(
        {**plan_filter, "status": "active"})
    completed_plans = await plans_collection.count_documents(
        {**plan_filter, "status": "completed"})

    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    report_scope = {
        "patient_id": {"$in": patient_keys},
        "event_type": "patient_report",
        "schema_version": 1,
        "source": "patient_self_report",
        "performed_at": {"$gte": month_start, "$lte": now},
    }
    reports = db["rehab_execution_events"]
    report_counts = {
        state: await reports.count_documents({**report_scope, "execution_status": state})
        for state in ("completed", "partial", "not_done")
    } if patient_keys else {"completed": 0, "partial": 0, "not_done": 0}
    patient_reports = {"total": sum(report_counts.values()), **report_counts,
                       "periodStart": month_start.isoformat() + "Z",
                       "periodEnd": now.isoformat() + "Z"}

    statistics: Dict[str, Any] = {
        "implemented": True,
        "patientCount": len(patient_keys),
        "rehabPlans": {
            "total": total_plans,
            "active": active_plans,
            "completed": completed_plans,
        },
        "patientSelfReportsThisMonth": patient_reports,
    }

    if followup_service is not None:
        statistics["followUps"] = await collect_follow_up_statistics(
            followup_service, patient_keys)

    return statistics


# 数据统计
@router.get("/statistics", response_model=dict)
async def get_doctor_statistics(
    time_range: Optional[str] = "month",
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """获取医生工作统计数据（真实聚合，2026-11-08 替换存根空对象）

    字段语义（均来自真实集合，无数据时如实为 0）：
    - patientCount: 患者 practitioners 中关联该医生的真实患者数
    - rehabPlans:   该医生作为 practitioner_id 的康复计划总数/进行中/已完成
                    （rehab_plans 集合，status: active/completed）
    - patientSelfReportsThisMonth: 所属患者本月患者自报条数及状态分布；
                    按 performed_at、UTC 月初至当前时间统计，表示自述，不代表已核验场次
    - implemented:  显式标记端点已实现真实聚合

    聚合实现与健康管理师端共用 collect_work_statistics（唯一实现）。
    """
    if current_user.role != "doctor":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    try:
        statistics = await collect_work_statistics(
            db,
            operator_id=current_user.id,
            operator_role="doctor",
            plan_scope="owner",
            operator_label="医生",
        )
        statistics["timeRange"] = time_range
        return statistics
    except (HTTPException, AppBaseException):
        # PatientAccessError 与适配器的 LegacyPatientIdentityError 均为 AppBaseException
        raise
    except Exception as e:
        print(f"获取医生统计数据时出错: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取医生统计数据失败，请稍后重试"
        )

# 知情同意
@router.get("/informed-consents", response_model=List[dict])
async def get_informed_consents(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """获取当前医生发出的知情同意。"""
    if current_user.role != "doctor":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    from app.directory.records import list_consents
    return await list_consents(db, current_user)
