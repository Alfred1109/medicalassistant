"""
基础模型类，用于所有schema
"""
from pydantic import BaseModel, Field
from typing import Optional, Any, ClassVar, Dict
from datetime import datetime
from bson import ObjectId
from pydantic_core import core_schema


_UNSET = object()
_OBJECT_ID_PATTERN = r"^[0-9a-fA-F]{24}$"


class PyObjectId(str):
    """
    MongoDB ObjectId的封装类，使其兼容Pydantic模型
    """
    def __new__(cls, value=_UNSET):
        # Several DB/attachment models use this class as their default factory.
        # An omitted value creates a new ID; explicit null is invalid input.
        if value is _UNSET:
            value = ObjectId()
        if not isinstance(value, (str, ObjectId)) or not ObjectId.is_valid(value):
            raise ValueError("Invalid ObjectId")
        return super().__new__(cls, str(value))

    @classmethod
    def validate(cls, v):
        return cls(v)

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):
        return core_schema.no_info_plain_validator_function(
            cls.validate,
            serialization=core_schema.to_string_ser_schema(when_used="json"),
        )

    @classmethod
    def __get_pydantic_json_schema__(cls, schema, handler):
        # A v2 handler is callable; it is not the mutable v1 field-schema dict.
        return handler(core_schema.str_schema(pattern=_OBJECT_ID_PATTERN))


class TimestampModel(BaseModel):
    """
    包含创建和更新时间的基础模型
    """
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(default_factory=datetime.utcnow)

    model_config: ClassVar[Dict[str, Any]] = {
        "json_encoders": {
            datetime: lambda dt: dt.isoformat(),
            ObjectId: lambda oid: str(oid)
        }
    }


# 添加一个通用的配置类，适配Pydantic V2
class PydanticConfig:
    """用于适配Pydantic V2的通用配置类"""
    from_attributes = True  # 替代 orm_mode
    populate_by_name = True  # 替代 allow_population_by_field_name
    json_encoders = {
        datetime: lambda dt: dt.isoformat()
    }
    
    @classmethod
    def get_json_schema_extra(cls, schema):
        """替代 schema_extra"""
        return schema
