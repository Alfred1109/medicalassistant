"""
工具函数模块
提供各种通用辅助函数
"""
from typing import Any, Dict, List, Optional, Union
from datetime import datetime, date
from bson import ObjectId
import json
import re
import uuid
from pydantic import BaseModel

# 文档转换相关函数
def format_object_id(obj_id: Union[str, ObjectId]) -> str:
    """将ObjectId转换为字符串"""
    if isinstance(obj_id, ObjectId):
        return str(obj_id)
    return obj_id


def format_datetime(dt: Union[datetime, date]) -> str:
    """格式化日期时间为ISO 8601字符串"""
    if isinstance(dt, datetime):
        return dt.isoformat()
    elif isinstance(dt, date):
        return dt.isoformat()
    return dt


def format_document(doc: Dict[str, Any]) -> Dict[str, Any]:
    """格式化MongoDB文档为API友好格式"""
    if not doc:
        return {}
    
    formatted = {}
    for key, value in doc.items():
        # 处理_id字段
        if key == '_id':
            formatted['id'] = format_object_id(value)
            continue
            
        # 递归处理嵌套字典
        if isinstance(value, dict):
            formatted[key] = format_document(value)
            continue
            
        # 处理数组
        if isinstance(value, list):
            formatted[key] = [
                format_document(item) if isinstance(item, dict) else 
                format_object_id(item) if isinstance(item, ObjectId) else
                format_datetime(item) if isinstance(item, (datetime, date)) else 
                item
                for item in value
            ]
            continue
            
        # 处理ObjectId
        if isinstance(value, ObjectId):
            formatted[key] = format_object_id(value)
            continue
            
        # 处理日期时间
        if isinstance(value, (datetime, date)):
            formatted[key] = format_datetime(value)
            continue
            
        # 其他类型保持不变
        formatted[key] = value
        
    return formatted


# 对象转换函数
def model_to_dict(model: BaseModel) -> Dict[str, Any]:
    """将Pydantic模型转换为字典"""
    return json.loads(model.model_dump_json())


def snake_to_camel(snake_str: str) -> str:
    """
    将蛇形命名转换为驼峰命名
    例如：user_name -> userName
    """
    components = snake_str.split('_')
    return components[0] + ''.join(x.title() for x in components[1:])


def camel_to_snake(camel_str: str) -> str:
    """
    将驼峰命名转换为蛇形命名
    例如：userName -> user_name
    """
    snake_str = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', camel_str)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', snake_str).lower()


def convert_keys(obj: Any, converter_func) -> Any:
    """通用键名转换函数，支持嵌套字典和列表"""
    if isinstance(obj, dict):
        return {
            converter_func(k): convert_keys(v, converter_func)
            for k, v in obj.items()
        }
    elif isinstance(obj, list):
        return [convert_keys(item, converter_func) for item in obj]
    return obj


def dict_to_camel_case(data: Dict[str, Any]) -> Dict[str, Any]:
    """将字典的键名转换为驼峰命名"""
    return convert_keys(data, snake_to_camel)


def dict_to_snake_case(data: Dict[str, Any]) -> Dict[str, Any]:
    """将字典的键名转换为蛇形命名"""
    return convert_keys(data, camel_to_snake)


# 通用函数
def generate_uuid() -> str:
    """生成UUID字符串"""
    return str(uuid.uuid4())


def truncate_string(text: str, max_length: int = 100) -> str:
    """截断字符串，超出部分用省略号替代"""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."


def is_valid_object_id(value: str) -> bool:
    """检查字符串是否是有效的ObjectId"""
    try:
        ObjectId(value)
        return True
    except:
        return False


def safe_get(obj: Dict[str, Any], key_path: str, default: Any = None) -> Any:
    """
    安全地从嵌套字典中获取值
    使用点表示法，例如: "user.profile.name"
    """
    keys = key_path.split('.')
    result = obj
    
    for key in keys:
        if isinstance(result, dict) and key in result:
            result = result[key]
        else:
            return default
            
    return result


def filter_none_values(data: Dict[str, Any]) -> Dict[str, Any]:
    """过滤字典中的None值"""
    return {k: v for k, v in data.items() if v is not None}


def merge_dicts(dict1: Dict[str, Any], dict2: Dict[str, Any]) -> Dict[str, Any]:
    """
    合并两个字典，支持嵌套合并
    dict2的值会覆盖dict1中同名键的值
    """
    result = dict1.copy()
    
    for key, value in dict2.items():
        if (
            key in result and 
            isinstance(result[key], dict) and 
            isinstance(value, dict)
        ):
            result[key] = merge_dicts(result[key], value)
        else:
            result[key] = value
            
    return result 