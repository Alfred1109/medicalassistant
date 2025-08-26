"""
缓存模块
提供内存缓存和缓存装饰器
"""
import time
import hashlib
import inspect
import json
from typing import Any, Callable, Dict, Optional, Tuple, Union, TypeVar, cast
from functools import wraps
import asyncio
from datetime import datetime, timedelta

from app.core.config import settings
from app.core.logging import app_logger as logger

# 类型变量
T = TypeVar('T')
F = TypeVar('F', bound=Callable[..., Any])

# 简单的内存缓存
class Cache:
    """简单的内存缓存实现"""
    
    def __init__(self):
        self._cache: Dict[str, Tuple[Any, float]] = {}
        self._lock = asyncio.Lock()
    
    async def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        if not settings.CACHE_ENABLED:
            return None
            
        if key not in self._cache:
            return None
            
        value, expire_time = self._cache[key]
        if expire_time < time.time():
            # 过期清理
            await self.delete(key)
            return None
            
        return value
    
    async def set(self, key: str, value: Any, ttl: int = None) -> None:
        """设置缓存值"""
        if not settings.CACHE_ENABLED:
            return
            
        ttl = ttl or settings.CACHE_TTL_SECONDS
        expire_time = time.time() + ttl
        
        async with self._lock:
            self._cache[key] = (value, expire_time)
    
    async def delete(self, key: str) -> None:
        """删除缓存值"""
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
    
    async def clear(self) -> None:
        """清空所有缓存"""
        async with self._lock:
            self._cache.clear()
    
    async def delete_pattern(self, pattern: str) -> int:
        """删除匹配特定模式的缓存键"""
        count = 0
        async with self._lock:
            keys_to_delete = [k for k in self._cache.keys() if pattern in k]
            for key in keys_to_delete:
                del self._cache[key]
                count += 1
        return count
    
    def size(self) -> int:
        """获取缓存大小"""
        return len(self._cache)


# 全局缓存实例
cache = Cache()


def generate_cache_key(prefix: str, *args, **kwargs) -> str:
    """生成缓存键"""
    # 将参数转换为JSON字符串
    key_parts = [prefix]
    
    if args:
        key_parts.append(json.dumps(args, sort_keys=True))
    
    if kwargs:
        key_parts.append(json.dumps(kwargs, sort_keys=True))
    
    # 使用md5生成缓存键
    key = hashlib.md5("".join(key_parts).encode()).hexdigest()
    return f"{prefix}:{key}"


def cached(ttl: Optional[int] = None, key_prefix: Optional[str] = None):
    """
    缓存装饰器，用于缓存函数返回值
    
    参数:
    - ttl: 缓存有效期（秒）
    - key_prefix: 缓存键前缀
    """
    def decorator(func: F) -> F:
        if not settings.CACHE_ENABLED:
            return func
            
        # 如果没有提供前缀，使用函数名
        prefix = key_prefix or f"cache:{func.__module__}:{func.__name__}"
        
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # 生成缓存键
            cache_key = generate_cache_key(prefix, *args, **kwargs)
            
            # 尝试从缓存获取
            cached_result = await cache.get(cache_key)
            if cached_result is not None:
                logger.debug(f"Cache hit: {cache_key}")
                return cached_result
                
            # 缓存未命中，执行原函数
            logger.debug(f"Cache miss: {cache_key}")
            result = await func(*args, **kwargs)
            
            # 缓存结果
            await cache.set(cache_key, result, ttl)
            return result
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # 对于同步函数，我们使用事件循环运行异步缓存操作
            
            # 生成缓存键
            cache_key = generate_cache_key(prefix, *args, **kwargs)
            
            # 尝试从缓存获取
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                # 没有事件循环，创建一个新的
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
            cached_result = loop.run_until_complete(cache.get(cache_key))
            if cached_result is not None:
                logger.debug(f"Cache hit: {cache_key}")
                return cached_result
                
            # 缓存未命中，执行原函数
            logger.debug(f"Cache miss: {cache_key}")
            result = func(*args, **kwargs)
            
            # 缓存结果
            loop.run_until_complete(cache.set(cache_key, result, ttl))
            return result
        
        # 根据函数是否为异步函数选择包装器
        if asyncio.iscoroutinefunction(func):
            return cast(F, async_wrapper)
        return cast(F, sync_wrapper)
        
    return decorator


async def invalidate_cache(pattern: str) -> int:
    """
    使特定模式的缓存无效
    
    参数:
    - pattern: 缓存键模式
    
    返回:
    - 被删除的缓存条目数
    """
    return await cache.delete_pattern(pattern) 