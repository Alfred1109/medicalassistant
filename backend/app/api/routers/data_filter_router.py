"""
数据过滤路由
提供高级数据过滤和查询相关的API接口
"""
from fastapi import APIRouter, Depends, HTTPException, Body, Query, Path
from typing import List, Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field

from ...services.data_filter_service import data_filter_service
from ...auth.jwt_auth import get_current_user

router = APIRouter(prefix="/data-filters", tags=["data-filters"])


# 数据模型
class FilterCondition(BaseModel):
    id: str = Field(..., description="条件ID")
    field: str = Field(..., description="字段名称")
    operator: str = Field(..., description="操作符")
    value: Any = Field(None, description="比较值")
    type: str = Field("string", description="值类型")
    logic: Optional[str] = Field(None, description="逻辑运算符")


class FilterRequest(BaseModel):
    collection: str = Field(..., description="集合名称")
    conditions: List[FilterCondition] = Field(..., description="过滤条件")
    sortField: Optional[str] = Field(None, description="排序字段")
    sortOrder: int = Field(1, description="排序顺序")
    skip: int = Field(0, description="跳过记录数")
    limit: int = Field(100, description="返回记录数")
    projection: Optional[Dict[str, int]] = Field(None, description="投影配置")


class SavedFilterRequest(BaseModel):
    name: str = Field(..., description="过滤器名称")
    description: Optional[str] = Field(None, description="过滤器描述")
    collection: str = Field(..., description="集合名称")
    conditions: List[FilterCondition] = Field(..., description="过滤条件")
    global_: bool = Field(False, description="是否为全局过滤器", alias="global")
    sortField: Optional[str] = Field(None, description="排序字段")
    sortOrder: Optional[int] = Field(None, description="排序顺序")


class FilterUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, description="过滤器名称")
    description: Optional[str] = Field(None, description="过滤器描述")
    conditions: Optional[List[FilterCondition]] = Field(None, description="过滤条件")
    global_: Optional[bool] = Field(None, description="是否为全局过滤器", alias="global")
    sortField: Optional[str] = Field(None, description="排序字段")
    sortOrder: Optional[int] = Field(None, description="排序顺序")


class SavedFilterResponse(BaseModel):
    id: str = Field(..., description="过滤器ID")
    name: str = Field(..., description="过滤器名称")
    description: Optional[str] = Field(None, description="过滤器描述")
    collection: str = Field(..., description="集合名称")
    conditions: List[FilterCondition] = Field(..., description="过滤条件")
    global_: bool = Field(False, description="是否为全局过滤器", alias="global")
    createdAt: datetime = Field(..., description="创建时间")
    createdBy: str = Field(..., description="创建者ID")
    createdByName: Optional[str] = Field(None, description="创建者名称")
    sortField: Optional[str] = Field(None, description="排序字段")
    sortOrder: Optional[int] = Field(None, description="排序顺序")

    class Config:
        allow_population_by_field_name = True


class FieldInfo(BaseModel):
    name: str = Field(..., description="字段名称")
    label: str = Field(..., description="字段标签")
    type: str = Field(..., description="字段类型")
    samples: List[str] = Field(..., description="样本值")
    coverage: float = Field(..., description="覆盖率")


class FilterResult(BaseModel):
    total: int = Field(..., description="总记录数")
    data: List[Dict[str, Any]] = Field(..., description="过滤结果")


# 数据转换
def format_filter(filter_data: Dict[str, Any]) -> Dict[str, Any]:
    """格式化过滤器数据"""
    return {
        "id": filter_data.get("_id"),
        "name": filter_data.get("name"),
        "description": filter_data.get("description"),
        "collection": filter_data.get("collection"),
        "conditions": filter_data.get("conditions", []),
        "global": filter_data.get("global", False),
        "createdAt": filter_data.get("createdAt"),
        "createdBy": filter_data.get("createdBy"),
        "createdByName": filter_data.get("createdByName"),
        "sortField": filter_data.get("sortField"),
        "sortOrder": filter_data.get("sortOrder")
    }


# API端点
@router.post("/apply", response_model=FilterResult)
async def apply_filter(
    filter_request: FilterRequest = Body(...),
    current_user: dict = Depends(get_current_user)
):
    """
    应用过滤条件查询数据
    
    参数:
    - filter_request: 过滤请求
    
    返回:
    - 符合条件的数据
    """
    try:
        # 验证集合名称有效性
        if not filter_request.collection:
            raise HTTPException(status_code=400, detail="集合名称不能为空")
        
        # 应用过滤条件
        results = await data_filter_service.apply_filter(
            collection_name=filter_request.collection,
            conditions=[condition.dict() for condition in filter_request.conditions],
            sort_field=filter_request.sortField,
            sort_order=filter_request.sortOrder,
            skip=filter_request.skip,
            limit=filter_request.limit,
            projection=filter_request.projection
        )
        
        # 获取总记录数
        total = await data_filter_service.count_filtered(
            collection_name=filter_request.collection,
            conditions=[condition.dict() for condition in filter_request.conditions]
        )
        
        return {"total": total, "data": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"应用过滤条件失败: {str(e)}")


@router.get("/schema/{collection}", response_model=List[FieldInfo])
async def get_collection_schema(
    collection: str = Path(..., description="集合名称"),
    current_user: dict = Depends(get_current_user)
):
    """
    获取集合字段结构
    
    参数:
    - collection: 集合名称
    
    返回:
    - 字段信息列表
    """
    try:
        # 获取集合结构
        fields = await data_filter_service.get_collection_schema(collection)
        return fields
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取集合结构失败: {str(e)}")


@router.post("/save", response_model=Dict[str, str])
async def save_filter(
    filter_data: SavedFilterRequest = Body(...),
    current_user: dict = Depends(get_current_user)
):
    """
    保存过滤器配置
    
    参数:
    - filter_data: 过滤器配置
    
    返回:
    - 过滤器ID
    """
    # 验证权限
    if filter_data.global_ and current_user.get("role") not in ["admin"]:
        raise HTTPException(status_code=403, detail="只有管理员可以创建全局过滤器")
    
    try:
        # 准备数据
        data = filter_data.dict(by_alias=True)
        data["createdBy"] = current_user.get("_id")
        data["createdByName"] = current_user.get("name") or current_user.get("username")
        
        # 保存过滤器
        filter_id = await data_filter_service.save_filter(data)
        return {"id": filter_id, "message": "过滤器保存成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存过滤器失败: {str(e)}")


@router.put("/{filter_id}", response_model=Dict[str, str])
async def update_filter(
    filter_id: str = Path(..., description="过滤器ID"),
    filter_data: FilterUpdateRequest = Body(...),
    current_user: dict = Depends(get_current_user)
):
    """
    更新过滤器配置
    
    参数:
    - filter_id: 过滤器ID
    - filter_data: 更新的过滤器配置
    
    返回:
    - 更新结果
    """
    # 获取现有过滤器
    existing_filter = await data_filter_service.get_filter(filter_id)
    if not existing_filter:
        raise HTTPException(status_code=404, detail="过滤器不存在")
    
    # 验证权限
    if (current_user.get("role") not in ["admin"] and 
        existing_filter.get("createdBy") != current_user.get("_id")):
        raise HTTPException(status_code=403, detail="没有权限更新此过滤器")
    
    # 如果更新全局状态，验证权限
    if filter_data.global_ and current_user.get("role") not in ["admin"]:
        raise HTTPException(status_code=403, detail="只有管理员可以创建全局过滤器")
    
    try:
        # 准备更新数据
        update_data = filter_data.dict(by_alias=True, exclude_unset=True)
        
        # 更新过滤器
        success = await data_filter_service.update_filter(filter_id, update_data)
        if success:
            return {"message": "过滤器更新成功"}
        else:
            raise HTTPException(status_code=500, detail="更新过滤器失败")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新过滤器失败: {str(e)}")


@router.delete("/{filter_id}", response_model=Dict[str, str])
async def delete_filter(
    filter_id: str = Path(..., description="过滤器ID"),
    current_user: dict = Depends(get_current_user)
):
    """
    删除过滤器
    
    参数:
    - filter_id: 过滤器ID
    
    返回:
    - 删除结果
    """
    # 获取现有过滤器
    existing_filter = await data_filter_service.get_filter(filter_id)
    if not existing_filter:
        raise HTTPException(status_code=404, detail="过滤器不存在")
    
    # 验证权限
    if (current_user.get("role") not in ["admin"] and 
        existing_filter.get("createdBy") != current_user.get("_id")):
        raise HTTPException(status_code=403, detail="没有权限删除此过滤器")
    
    try:
        # 删除过滤器
        success = await data_filter_service.delete_filter(filter_id)
        if success:
            return {"message": "过滤器删除成功"}
        else:
            raise HTTPException(status_code=500, detail="删除过滤器失败")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除过滤器失败: {str(e)}")


@router.get("", response_model=List[SavedFilterResponse])
async def get_filters(
    collection: Optional[str] = Query(None, description="集合名称"),
    global_only: bool = Query(False, description="是否只返回全局过滤器"),
    current_user: dict = Depends(get_current_user)
):
    """
    获取保存的过滤器列表
    
    参数:
    - collection: 可选，集合名称
    - global_only: 是否只返回全局过滤器
    
    返回:
    - 过滤器列表
    """
    try:
        # 获取过滤器列表
        filters = await data_filter_service.get_saved_filters(
            user_id=current_user.get("_id"),
            collection=collection,
            global_only=global_only
        )
        
        # 格式化结果
        return [format_filter(filter_data) for filter_data in filters]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取过滤器列表失败: {str(e)}")


@router.get("/{filter_id}", response_model=SavedFilterResponse)
async def get_filter(
    filter_id: str = Path(..., description="过滤器ID"),
    current_user: dict = Depends(get_current_user)
):
    """
    获取单个过滤器配置
    
    参数:
    - filter_id: 过滤器ID
    
    返回:
    - 过滤器配置
    """
    # 获取过滤器
    filter_data = await data_filter_service.get_filter(filter_id)
    if not filter_data:
        raise HTTPException(status_code=404, detail="过滤器不存在")
    
    # 验证权限
    if (not filter_data.get("global", False) and 
        current_user.get("role") not in ["admin"] and 
        filter_data.get("createdBy") != current_user.get("_id")):
        raise HTTPException(status_code=403, detail="没有权限查看此过滤器")
    
    # 格式化并返回
    return format_filter(filter_data) 