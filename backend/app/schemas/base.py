"""
基础模型类，用于所有schema
"""
from pydantic import BaseModel, Field
from typing import Optional, Any, ClassVar, Dict
from datetime import datetime
from bson import ObjectId


class PyObjectId(str):
    """
    MongoDB ObjectId的封装类，使其兼容Pydantic模型
    """
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not ObjectId.is_valid(str(v)):
            raise ValueError("Invalid ObjectId")
        return str(v)

    @classmethod
    def __get_pydantic_json_schema__(cls, _schema_generator, field_schema):
        field_schema.update(type="string")
        return field_schema


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