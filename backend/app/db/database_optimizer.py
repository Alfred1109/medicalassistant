"""
数据库优化工具
提供MongoDB索引分析、查询优化和连接池管理功能
"""
import os
import time
import logging
import asyncio
from typing import Dict, List, Any, Optional, Tuple, Set
from datetime import datetime, timedelta
from pymongo import ASCENDING, DESCENDING
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from functools import wraps

from ..core.config import settings

# 配置日志
logger = logging.getLogger(__name__)

# 慢查询阈值(毫秒)
SLOW_QUERY_THRESHOLD = 200  

# 查询缓存有效期(秒)
QUERY_CACHE_TTL = 300  

# 查询缓存
_query_cache: Dict[str, Tuple[Any, datetime]] = {}

class DatabaseOptimizer:
    """数据库优化工具类，提供索引分析、查询优化和连接池管理功能"""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        """初始化数据库优化器"""
        self.db = db
        self.monitored_collections: Set[str] = set()
        self.slow_queries: List[Dict[str, Any]] = []
        self.index_usage_stats: Dict[str, Dict[str, int]] = {}
    
    async def analyze_indexes(self, collection_name: str) -> Dict[str, Any]:
        """
        分析集合的索引使用情况
        
        参数:
            collection_name: 集合名称
            
        返回:
            索引分析结果
        """
        try:
            # 获取索引列表
            indexes = await self.db[collection_name].index_information()
            
            # 获取索引统计信息
            stats = await self.db.command({
                "aggregate": collection_name,
                "pipeline": [{"$indexStats": {}}],
                "cursor": {}
            })
            
            # 提取索引使用情况
            index_stats = {}
            for stat in stats["cursor"]["firstBatch"]:
                index_name = stat["name"]
                index_stats[index_name] = {
                    "usage_count": stat.get("accesses", {}).get("ops", 0),
                    "since": stat.get("accesses", {}).get("since", None)
                }
            
            # 合并索引信息
            result = {
                "collection": collection_name,
                "indexes": [],
                "recommendations": []
            }
            
            for name, idx in indexes.items():
                # 获取索引使用统计
                usage = index_stats.get(name, {"usage_count": 0, "since": None})
                
                # 收集索引详细信息
                index_info = {
                    "name": name,
                    "keys": idx["key"],
                    "unique": idx.get("unique", False),
                    "sparse": idx.get("sparse", False),
                    "usage_count": usage["usage_count"],
                    "since": usage["since"]
                }
                
                result["indexes"].append(index_info)
                
                # 生成优化建议
                if name != "_id_" and usage["usage_count"] == 0 and usage["since"]:
                    # 检查索引创建时间，如果超过一周未使用，建议移除
                    since_date = usage["since"]
                    if isinstance(since_date, datetime) and (datetime.utcnow() - since_date) > timedelta(days=7):
                        result["recommendations"].append({
                            "type": "remove_index",
                            "index": name,
                            "reason": "索引未被使用超过一周"
                        })
            
            # 收集冗余索引信息
            self._detect_redundant_indexes(result)
            
            return result
            
        except Exception as e:
            logger.error(f"分析索引错误: {str(e)}")
            return {
                "collection": collection_name,
                "error": str(e),
                "indexes": [],
                "recommendations": []
            }
    
    def _detect_redundant_indexes(self, result: Dict[str, Any]):
        """检测冗余索引"""
        indexes = result["indexes"]
        
        # 检查包含关系的索引
        for i, idx1 in enumerate(indexes):
            if idx1["name"] == "_id_":
                continue
                
            keys1 = idx1["keys"]
            prefix_keys = [k for k, _ in keys1[:1]]  # 获取第一个键
            
            for j, idx2 in enumerate(indexes):
                if i == j or idx2["name"] == "_id_":
                    continue
                
                keys2 = idx2["keys"]
                
                # 检查是否有完全相同的键
                if keys1 == keys2 and idx1["name"] != idx2["name"]:
                    result["recommendations"].append({
                        "type": "redundant_index",
                        "indexes": [idx1["name"], idx2["name"]],
                        "reason": "完全相同的索引"
                    })
                    continue
                
                # 检查是否存在前缀包含关系
                if len(keys2) > len(keys1):
                    continue
                    
                # 检查idx2是否是idx1的前缀
                is_prefix = True
                for k in range(len(keys2)):
                    if keys2[k][0] != keys1[k][0] or keys2[k][1] != keys1[k][1]:
                        is_prefix = False
                        break
                
                if is_prefix:
                    result["recommendations"].append({
                        "type": "redundant_prefix",
                        "covered_index": idx2["name"],
                        "covering_index": idx1["name"],
                        "reason": f"索引 {idx1['name']} 包含了 {idx2['name']} 的所有键"
                    })
    
    async def suggest_new_indexes(self, collection_name: str, query_samples: List[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        基于查询样本建议新索引
        
        参数:
            collection_name: 集合名称
            query_samples: 查询样本列表
            
        返回:
            索引建议列表
        """
        try:
            # 获取集合对象
            collection = self.db[collection_name]
            
            # 获取现有索引
            existing_indexes = await collection.index_information()
            existing_keys = set()
            
            for _, idx in existing_indexes.items():
                # 将索引键转换为字符串形式
                key_str = ",".join([f"{k}_{d}" for k, d in idx["key"]])
                existing_keys.add(key_str)
            
            # 如果没有提供查询样本，使用慢查询记录
            if not query_samples:
                query_samples = [q["query"] for q in self.slow_queries if q["collection"] == collection_name]
            
            # 分析查询样本，生成索引建议
            suggestions = []
            
            for query in query_samples:
                # 跳过空查询
                if not query:
                    continue
                
                # 从查询中提取可能的索引字段
                candidate_fields = self._extract_index_fields(query)
                
                for field, direction in candidate_fields:
                    # 检查是否已存在相应索引
                    key_str = f"{field}_{direction}"
                    
                    if key_str not in existing_keys and not any(s["field"] == field for s in suggestions):
                        suggestions.append({
                            "field": field,
                            "direction": direction,
                            "command": f'db.{collection_name}.createIndex({{ "{field}": {direction} }})'
                        })
            
            return suggestions
            
        except Exception as e:
            logger.error(f"生成索引建议错误: {str(e)}")
            return []
    
    def _extract_index_fields(self, query: Dict[str, Any]) -> List[Tuple[str, int]]:
        """从查询中提取可能需要索引的字段"""
        fields = []
        
        # 处理简单查询条件
        for field, value in query.items():
            # 跳过MongoDB操作符
            if field.startswith('$'):
                continue
                
            if isinstance(value, dict) and any(k.startswith('$') for k in value.keys()):
                # 排序字段优先考虑
                if '$sort' in value:
                    direction = value['$sort']
                    fields.append((field, direction if direction in [1, -1] else 1))
                # 范围查询
                elif any(k in ['$gt', '$gte', '$lt', '$lte'] for k in value.keys()):
                    fields.append((field, 1))
                # 相等性查询
                elif '$eq' in value:
                    fields.append((field, 1))
            else:
                # 直接相等查询
                fields.append((field, 1))
        
        return fields
    
    async def monitor_slow_queries(self, enable: bool = True):
        """
        开启或关闭慢查询监控
        
        参数:
            enable: 是否启用监控
        """
        if enable:
            # 开启profiling
            await self.db.command({
                "profile": 1,
                "slowms": SLOW_QUERY_THRESHOLD
            })
            logger.info(f"已开启慢查询监控，阈值: {SLOW_QUERY_THRESHOLD}ms")
        else:
            # 关闭profiling
            await self.db.command({"profile": 0})
            logger.info("已关闭慢查询监控")
    
    async def get_slow_queries(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        获取慢查询列表
        
        参数:
            limit: 返回结果数量限制
            
        返回:
            慢查询列表
        """
        try:
            # 查询profile集合
            system_profile = self.db.system.profile
            
            # 获取最近的慢查询
            cursor = system_profile.find().sort("ts", -1).limit(limit)
            
            slow_queries = []
            async for doc in cursor:
                # 提取关键信息
                query_info = {
                    "operation": doc.get("op"),
                    "collection": doc.get("ns", "").split(".")[-1],
                    "query": doc.get("command") or doc.get("query"),
                    "execution_time_ms": doc.get("millis"),
                    "timestamp": doc.get("ts"),
                    "client": doc.get("client"),
                    "user": doc.get("user")
                }
                
                # 添加执行计划信息
                if "planSummary" in doc:
                    query_info["plan_summary"] = doc["planSummary"]
                
                slow_queries.append(query_info)
            
            return slow_queries
            
        except Exception as e:
            logger.error(f"获取慢查询错误: {str(e)}")
            return []
    
    async def optimize_query(self, collection_name: str, query: Dict[str, Any]) -> Dict[str, Any]:
        """
        优化查询，提供执行计划和改进建议
        
        参数:
            collection_name: 集合名称
            query: 查询条件
            
        返回:
            优化建议
        """
        try:
            # 获取集合对象
            collection = self.db[collection_name]
            
            # 执行explain
            explanation = await collection.find(query).explain()
            
            # 分析执行计划
            stage = explanation.get("queryPlanner", {}).get("winningPlan", {})
            
            optimization_result = {
                "original_query": query,
                "collection": collection_name,
                "execution_stats": {},
                "suggestions": []
            }
            
            # 添加执行统计信息(如果可用)
            if "executionStats" in explanation:
                stats = explanation["executionStats"]
                optimization_result["execution_stats"] = {
                    "execution_time_ms": stats.get("executionTimeMillis"),
                    "docs_examined": stats.get("totalDocsExamined"),
                    "docs_returned": stats.get("nReturned"),
                    "index_used": stats.get("indexName", "None")
                }
            
            # 检查是否进行了COLLSCAN
            is_collection_scan = False
            if "inputStage" in stage:
                if stage.get("stage") == "COLLSCAN":
                    is_collection_scan = True
                elif stage.get("inputStage", {}).get("stage") == "COLLSCAN":
                    is_collection_scan = True
            
            # 如果是全集合扫描，建议添加索引
            if is_collection_scan:
                # 生成索引建议
                index_suggestions = await self.suggest_new_indexes(collection_name, [query])
                
                if index_suggestions:
                    optimization_result["suggestions"].extend([
                        {
                            "type": "add_index",
                            "reason": "查询执行了全集合扫描，性能可能较差",
                            "index": suggestion
                        }
                        for suggestion in index_suggestions
                    ])
            
            # 检查返回文档数量与扫描文档数量比例
            if "execution_stats" in optimization_result:
                stats = optimization_result["execution_stats"]
                docs_returned = stats.get("docs_returned", 0)
                docs_examined = stats.get("docs_examined", 0)
                
                if docs_examined > 0 and docs_returned > 0:
                    ratio = docs_returned / docs_examined
                    
                    if ratio < 0.1 and docs_examined > 100:
                        optimization_result["suggestions"].append({
                            "type": "improve_selectivity",
                            "reason": f"查询效率低下，仅返回了扫描文档的{ratio:.1%}",
                            "recommendation": "优化查询条件，提高选择性，或创建更精确的索引"
                        })
            
            # 检查查询投影
            if not any(k.startswith("$") for k in query.keys()) and len(query.keys()) > 0:
                optimization_result["suggestions"].append({
                    "type": "use_projection",
                    "reason": "未使用投影，可能返回了不必要的字段",
                    "recommendation": "使用投影仅返回需要的字段，例如 collection.find(query, {field1: 1, field2: 1})"
                })
            
            return optimization_result
            
        except Exception as e:
            logger.error(f"优化查询错误: {str(e)}")
            return {
                "original_query": query,
                "collection": collection_name,
                "error": str(e),
                "suggestions": []
            }
    
    async def analyze_all_collections(self) -> Dict[str, Any]:
        """
        分析所有集合的索引和性能状况
        
        返回:
            分析结果
        """
        try:
            # 获取所有集合
            collections = await self.db.list_collection_names()
            
            # 分析结果
            analysis = {
                "collections": [],
                "total_indexes": 0,
                "redundant_indexes": 0,
                "unused_indexes": 0,
                "recommendations": []
            }
            
            # 分析每个集合
            for collection_name in collections:
                # 跳过系统集合
                if collection_name.startswith("system."):
                    continue
                
                # 分析索引
                index_analysis = await self.analyze_indexes(collection_name)
                
                # 计算统计信息
                collection_stats = {
                    "name": collection_name,
                    "index_count": len(index_analysis["indexes"]),
                    "recommendation_count": len(index_analysis["recommendations"])
                }
                
                # 更新总计
                analysis["total_indexes"] += collection_stats["index_count"]
                analysis["collections"].append(collection_stats)
                
                # 处理建议
                for rec in index_analysis["recommendations"]:
                    if rec["type"] in ["redundant_index", "redundant_prefix"]:
                        analysis["redundant_indexes"] += 1
                    elif rec["type"] == "remove_index":
                        analysis["unused_indexes"] += 1
                    
                    # 添加集合上下文
                    rec["collection"] = collection_name
                    analysis["recommendations"].append(rec)
            
            return analysis
            
        except Exception as e:
            logger.error(f"分析所有集合错误: {str(e)}")
            return {
                "error": str(e),
                "collections": [],
                "recommendations": []
            }
    
    @staticmethod
    async def optimize_connection_pool(client: AsyncIOMotorClient, min_pool_size: int = 10, max_pool_size: int = 50):
        """
        优化MongoDB连接池设置
        
        参数:
            client: MongoDB客户端
            min_pool_size: 最小连接池大小
            max_pool_size: 最大连接池大小
        """
        try:
            # 由于Motor连接池已在创建客户端时配置，这里只是记录
            logger.info(f"MongoDB连接池配置: 最小连接数={min_pool_size}, 最大连接数={max_pool_size}")
            
            # 获取服务器状态
            db = client.admin
            server_status = await db.command({"serverStatus": 1})
            
            # 记录连接统计信息
            if "connections" in server_status:
                conn_stats = server_status["connections"]
                logger.info(f"MongoDB连接统计: 当前={conn_stats.get('current')}, "
                           f"可用={conn_stats.get('available')}, 总计={conn_stats.get('totalCreated')}")
        except Exception as e:
            logger.error(f"优化连接池错误: {str(e)}")


# 创建一个缓存装饰器，用于常用查询
def cached_query(ttl_seconds: int = QUERY_CACHE_TTL):
    """
    查询缓存装饰器
    
    参数:
        ttl_seconds: 缓存有效期（秒）
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 生成缓存键
            cache_key = f"{func.__name__}:{str(args)}:{str(kwargs)}"
            
            # 检查缓存
            if cache_key in _query_cache:
                result, timestamp = _query_cache[cache_key]
                # 判断缓存是否过期
                if datetime.utcnow() - timestamp < timedelta(seconds=ttl_seconds):
                    return result
            
            # 执行查询
            start_time = time.time()
            result = await func(*args, **kwargs)
            duration = time.time() - start_time
            
            # 记录查询耗时
            if duration > SLOW_QUERY_THRESHOLD / 1000:
                logger.warning(f"慢查询: {func.__name__} 耗时 {duration:.2f}秒")
            
            # 更新缓存
            _query_cache[cache_key] = (result, datetime.utcnow())
            
            # 清理过期缓存
            if len(_query_cache) > 1000:  # 避免缓存过大
                _clean_cache()
            
            return result
        return wrapper
    return decorator


def _clean_cache():
    """清理过期缓存"""
    now = datetime.utcnow()
    keys_to_delete = []
    
    for key, (_, timestamp) in _query_cache.items():
        if now - timestamp > timedelta(seconds=QUERY_CACHE_TTL):
            keys_to_delete.append(key)
    
    for key in keys_to_delete:
        del _query_cache[key]


# 创建一个异步任务，定期清理缓存
async def periodic_cache_cleanup():
    """定期清理缓存的异步任务"""
    while True:
        await asyncio.sleep(60)  # 每分钟执行一次
        _clean_cache()


# 获取优化器单例
_optimizer_instance = None

async def get_optimizer(db: AsyncIOMotorDatabase = None) -> DatabaseOptimizer:
    """
    获取数据库优化器实例
    
    参数:
        db: MongoDB数据库实例
        
    返回:
        DatabaseOptimizer实例
    """
    global _optimizer_instance
    
    if _optimizer_instance is None and db is not None:
        _optimizer_instance = DatabaseOptimizer(db)
        
        # 开启慢查询监控
        if settings.ENABLE_SLOW_QUERY_MONITORING:
            await _optimizer_instance.monitor_slow_queries(True)
        
        # 启动缓存清理任务
        asyncio.create_task(periodic_cache_cleanup())
    
    return _optimizer_instance 