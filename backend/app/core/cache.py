"""
缓存模块
提供内存缓存和缓存装饰器
"""
import time
import hashlib
import json
from typing import Any, Dict, Optional, Tuple
import asyncio

from app.core.config import settings

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