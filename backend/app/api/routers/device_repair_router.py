"""
设备修复路由
提供设备修复历史查询等接口
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from bson import ObjectId

from ...db.mongodb import get_db
from ...services.device_service import device_service
from ...auth.auth_utils import get_current_user

router = APIRouter(prefix="/device-repairs", tags=["device-repairs"])

@router.get("/history", response_model=List[Dict])
async def get_repair_history(
    device_id: Optional[str] = None,
    success: Optional[bool] = None,
    days: Optional[int] = 30,
    limit: Optional[int] = 50,
    current_user: Dict = Depends(get_current_user)
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
    # 检查用户权限
    if "doctor" not in current_user.get("roles", []) and "admin" not in current_user.get("roles", []):
        raise HTTPException(
            status_code=403,
            detail="权限不足，只有医生或管理员可以查看设备修复历史"
        )
    
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
    db = await get_db()
    repairs = await db.device_repair_logs.find(query).sort("repair_time", -1).limit(limit).to_list(None)
    
    # 转换ObjectId为字符串
    for repair in repairs:
        repair["_id"] = str(repair["_id"])
    
    return repairs

@router.get("/{repair_id}", response_model=Dict)
async def get_repair_details(
    repair_id: str,
    current_user: Dict = Depends(get_current_user)
):
    """
    获取单个设备修复记录的详细信息
    
    参数:
    - repair_id: 修复记录ID
    
    返回:
    - 修复记录详情
    """
    # 检查用户权限
    if "doctor" not in current_user.get("roles", []) and "admin" not in current_user.get("roles", []):
        raise HTTPException(
            status_code=403,
            detail="权限不足，只有医生或管理员可以查看设备修复详情"
        )
    
    db = await get_db()
    repair = await db.device_repair_logs.find_one({"_id": ObjectId(repair_id)})
    
    if not repair:
        raise HTTPException(
            status_code=404,
            detail="修复记录不存在"
        )
    
    # 转换ObjectId为字符串
    repair["_id"] = str(repair["_id"])
    
    return repair

@router.get("/device/{device_id}/summary", response_model=Dict)
async def get_device_repair_summary(
    device_id: str,
    days: Optional[int] = 90,
    current_user: Dict = Depends(get_current_user)
):
    """
    获取设备修复统计摘要
    
    参数:
    - device_id: 设备ID
    - days: 可选，查询最近多少天的记录，默认90天
    
    返回:
    - 修复统计摘要
    """
    # 检查用户权限
    if "doctor" not in current_user.get("roles", []) and "admin" not in current_user.get("roles", []):
        raise HTTPException(
            status_code=403,
            detail="权限不足，只有医生或管理员可以查看设备修复统计"
        )
    
    # 构建查询条件
    start_date = datetime.utcnow() - timedelta(days=days)
    query = {
        "device_id": device_id,
        "repair_time": {"$gte": start_date}
    }
    
    # 查询数据库
    db = await get_db()
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