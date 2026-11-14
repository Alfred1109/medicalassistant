"""
设备维修路由器
处理设备维修和修复记录相关API请求
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from bson import ObjectId

from ...db.mongodb import get_db, get_database
from ...services.device_service import device_service, DEVICE_READ_ROLES
from ...services.device_repair_service import device_repair_service
from ...core.dependencies import get_current_user
from ...core.device_access import device_patient_scope, ensure_device_access
from ...patients.legacy import LegacyPatientRepository


def _ensure_repair_log_read_access(current_user) -> None:
    """维修记录只读守卫。

    回归锁定：get_current_user 返回 pydantic UserResponse（.role 单角色字段），
    此前按 dict.get("roles", []) 访问必然 AttributeError → 500。
    语义统一（缺陷 B）：维修记录属设备数据只读路径，医疗 staff
    （doctor / health_manager / admin）可查看；患者与健康管理师变更之外
    的写角色不存在，此处不涉及变更操作。
    """
    if current_user.role not in DEVICE_READ_ROLES:
        raise HTTPException(
            status_code=403,
            detail="权限不足，只有医生、健康管理师或管理员可以查看设备维修记录"
        )

router = APIRouter(prefix="/device-repairs", tags=["device-repairs"])


async def _repair_device_access(db, device_id, actor):
    if actor.role == "admin":
        return
    if not isinstance(device_id, str) or not ObjectId.is_valid(device_id):
        raise HTTPException(404, detail="设备不存在")
    device = await db.devices.find_one({"_id": ObjectId(device_id)})
    if not device:
        raise HTTPException(404, detail="设备不存在")
    await ensure_device_access(db, device, actor, DEVICE_READ_ROLES)

@router.get("/history", response_model=List[Dict])
async def get_repair_history(
    device_id: Optional[str] = None,
    success: Optional[bool] = None,
    days: Optional[int] = 30,
    limit: Optional[int] = 50,
    current_user: Dict = Depends(get_current_user),
    db = Depends(get_database),
):
    """
    获取设备修复历史
    
    参数:
    - device_id: 可选，设备ID
    - success: 可选，是否只返回成功/失败的修复记录
    - days: 可选，查询最近多少天的记录，默认30天
    - limit: 可选，返回记录数量限制，默认50条
    
    返回:
    - 修复历史记录列表
    """
    # 检查用户权限（维修记录只读：医疗 staff 可查看）
    _ensure_repair_log_read_access(current_user)

    # 构建查询条件
    query = {}
    
    # 如果指定了设备ID
    if device_id:
        query["device_id"] = device_id
    
    # 如果指定了成功/失败状态
    if success is not None:
        query["overall_success"] = success
    
    # 如果指定了时间范围
    if days:
        start_date = datetime.utcnow() - timedelta(days=days)
        query["repair_time"] = {"$gte": start_date}
    
    # 查询数据库
    if device_id:
        await _repair_device_access(db, device_id, current_user)
    elif current_user.role != "admin":
        scope = await device_patient_scope(db, current_user)
        devices = await db.devices.find({"patient_id": {"$in": LegacyPatientRepository._identifiers(scope)},
                                        "status": {"$ne": "deleted"}}, {"_id": 1}).to_list(length=None)
        query["device_id"] = {"$in": [str(device["_id"]) for device in devices]}
    repairs = await db.device_repair_logs.find(query).sort("repair_time", -1).limit(limit).to_list(None)
    
    # 转换ObjectId为字符串
    for repair in repairs:
        repair["_id"] = str(repair["_id"])
    
    return repairs

@router.get("/{repair_id}", response_model=Dict)
async def get_repair_details(
    repair_id: str,
    current_user: Dict = Depends(get_current_user),
    db = Depends(get_database),
):
    """
    获取单个设备修复记录的详细信息
    
    参数:
    - repair_id: 修复记录ID
    
    返回:
    - 修复记录详情
    """
    # 检查用户权限（维修记录只读：医疗 staff 可查看）
    _ensure_repair_log_read_access(current_user)
    if not ObjectId.is_valid(repair_id):
        raise HTTPException(404, detail="修复记录不存在")

    repair = await db.device_repair_logs.find_one({"_id": ObjectId(repair_id)})
    
    if not repair:
        raise HTTPException(
            status_code=404,
            detail="修复记录不存在"
        )
    await _repair_device_access(db, repair.get("device_id"), current_user)
    
    # 转换ObjectId为字符串
    repair["_id"] = str(repair["_id"])
    
    return repair

@router.get("/device/{device_id}/summary", response_model=Dict)
async def get_device_repair_summary(
    device_id: str,
    days: Optional[int] = 90,
    current_user: Dict = Depends(get_current_user),
    db = Depends(get_database),
):
    """
    获取设备修复统计摘要
    
    参数:
    - device_id: 设备ID
    - days: 可选，查询最近多少天的记录，默认90天
    
    返回:
    - 修复统计摘要
    """
    # 检查用户权限（维修记录只读：医疗 staff 可查看）
    _ensure_repair_log_read_access(current_user)

    # 构建查询条件
    start_date = datetime.utcnow() - timedelta(days=days)
    query = {
        "device_id": device_id,
        "repair_time": {"$gte": start_date}
    }
    
    # 查询数据库
    await _repair_device_access(db, device_id, current_user)
    repairs = await db.device_repair_logs.find(query).to_list(None)
    
    # 统计数据
    total_repairs = len(repairs)
    successful_repairs = sum(1 for r in repairs if r.get("overall_success"))
    failed_repairs = total_repairs - successful_repairs
    
    # 计算成功率
    success_rate = round(successful_repairs / total_repairs * 100, 1) if total_repairs > 0 else 0
    
    # 统计最常见问题
    common_issues = {}
    for repair in repairs:
        for action in repair.get("repair_actions", []):
            common_issues[action] = common_issues.get(action, 0) + 1
    
    # 转换为列表并排序
    common_issues_list = [{"action": action, "count": count} for action, count in common_issues.items()]
    common_issues_list.sort(key=lambda x: x["count"], reverse=True)
    
    # 最近一次修复时间
    latest_repair_time = max([r.get("repair_time") for r in repairs]) if repairs else None
    
    return {
        "device_id": device_id,
        "total_repairs": total_repairs,
        "successful_repairs": successful_repairs,
        "failed_repairs": failed_repairs,
        "success_rate": success_rate,
        "common_issues": common_issues_list[:5],  # 取前5个最常见问题
        "latest_repair_time": latest_repair_time,
        "days_analyzed": days
    }
