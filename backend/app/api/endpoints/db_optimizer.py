"""
数据库优化工具API
提供索引分析、查询优化和性能监控功能
"""
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from motor.motor_asyncio import AsyncIOMotorDatabase

from ...db.mongodb import get_database
from ...db.database_optimizer import get_optimizer, DatabaseOptimizer
from ...models.user import User
from ...api.deps import get_current_admin, get_current_user

router = APIRouter()

@router.get("/analyze-indexes/{collection_name}")
async def analyze_collection_indexes(
    collection_name: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: User = Depends(get_current_admin)
) -> Dict[str, Any]:
    """
    分析集合的索引使用情况
    
    参数:
    - collection_name: 集合名称
    
    返回:
    - 索引分析结果，包括使用情况和优化建议
    """
    optimizer = await get_optimizer(db)
    result = await optimizer.analyze_indexes(collection_name)
    
    if "error" in result:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"分析索引错误: {result['error']}"
        )
    
    return result

@router.get("/analyze-all-collections")
async def analyze_all_collections(
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: User = Depends(get_current_admin)
) -> Dict[str, Any]:
    """
    分析所有集合的索引和性能状况
    
    返回:
    - 所有集合的索引分析结果和优化建议
    """
    optimizer = await get_optimizer(db)
    result = await optimizer.analyze_all_collections()
    
    if "error" in result:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"分析所有集合错误: {result['error']}"
        )
    
    return result

@router.get("/slow-queries")
async def get_slow_queries(
    limit: int = Query(20, description="返回的慢查询记录数量"),
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: User = Depends(get_current_admin)
) -> List[Dict[str, Any]]:
    """
    获取系统中的慢查询列表
    
    参数:
    - limit: 返回的记录数量上限
    
    返回:
    - 慢查询列表
    """
    optimizer = await get_optimizer(db)
    result = await optimizer.get_slow_queries(limit)
    
    return result

@router.post("/optimize-query/{collection_name}")
async def optimize_query(
    collection_name: str,
    query: Dict[str, Any],
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: User = Depends(get_current_admin)
) -> Dict[str, Any]:
    """
    优化查询，提供执行计划和改进建议
    
    参数:
    - collection_name: 集合名称
    - query: 查询条件
    
    返回:
    - 查询优化建议
    """
    optimizer = await get_optimizer(db)
    result = await optimizer.optimize_query(collection_name, query)
    
    if "error" in result:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"优化查询错误: {result['error']}"
        )
    
    return result

@router.post("/suggest-indexes/{collection_name}")
async def suggest_indexes(
    collection_name: str,
    query_samples: Optional[List[Dict[str, Any]]] = None,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: User = Depends(get_current_admin)
) -> List[Dict[str, Any]]:
    """
    基于查询样本为集合建议新索引
    
    参数:
    - collection_name: 集合名称
    - query_samples: 查询样本列表（可选）
    
    返回:
    - 索引建议列表
    """
    optimizer = await get_optimizer(db)
    result = await optimizer.suggest_new_indexes(collection_name, query_samples)
    
    return result

@router.post("/monitor-slow-queries")
async def set_slow_query_monitoring(
    enable: bool,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: User = Depends(get_current_admin)
) -> Dict[str, Any]:
    """
    开启或关闭慢查询监控
    
    参数:
    - enable: 是否启用监控
    
    返回:
    - 操作结果
    """
    optimizer = await get_optimizer(db)
    await optimizer.monitor_slow_queries(enable)
    
    return {
        "status": "success",
        "message": f"慢查询监控已{'开启' if enable else '关闭'}"
    }

@router.get("/db-status")
async def get_database_status(
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: User = Depends(get_current_admin)
) -> Dict[str, Any]:
    """
    获取数据库整体状态
    
    返回:
    - 数据库状态信息
    """
    try:
        # 获取数据库状态
        server_status = await db.command({"serverStatus": 1})
        
        # 提取关键指标
        connections = server_status.get("connections", {})
        mem_info = server_status.get("mem", {})
        op_counters = server_status.get("opcounters", {})
        
        # 获取数据库和集合信息
        db_stats = await db.command({"dbStats": 1})
        collection_count = db_stats.get("collections", 0)
        
        # 获取集合列表
        collections = await db.list_collection_names()
        
        return {
            "status": "success",
            "version": server_status.get("version", "未知"),
            "uptime_seconds": server_status.get("uptime", 0),
            "connections": {
                "current": connections.get("current", 0),
                "available": connections.get("available", 0),
                "total_created": connections.get("totalCreated", 0)
            },
            "memory_usage_mb": {
                "resident": mem_info.get("resident", 0),
                "virtual": mem_info.get("virtual", 0),
                "mapped": mem_info.get("mapped", 0)
            },
            "operations": {
                "inserts": op_counters.get("insert", 0),
                "queries": op_counters.get("query", 0),
                "updates": op_counters.get("update", 0),
                "deletes": op_counters.get("delete", 0),
                "getmores": op_counters.get("getmore", 0)
            },
            "collections": {
                "count": collection_count,
                "list": collections
            },
            "storage_size_mb": round(db_stats.get("storageSize", 0) / (1024 * 1024), 2),
            "data_size_mb": round(db_stats.get("dataSize", 0) / (1024 * 1024), 2),
            "index_size_mb": round(db_stats.get("indexSize", 0) / (1024 * 1024), 2)
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取数据库状态错误: {str(e)}"
        ) 