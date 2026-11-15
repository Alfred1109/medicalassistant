"""用户文档到响应模型的映射。

认证层需要把库里的用户文档变成角色响应，但不能因此 import UserService
（core 不得依赖 services）。映射只依赖 schema，UserService 的同名方法委托到这里。
"""
from typing import Any, Dict, Optional

from bson import ObjectId, errors

from app.schemas.user import (
    AdminResponse,
    DoctorResponse,
    HealthManagerResponse,
    PatientResponse,
    UserResponse,
)


def user_response_from_document(user: Dict[str, Any]) -> UserResponse:
    """Map a user document to a UserResponse schema."""
    stored_password = user.get("hashed_password") or ""
    base_user = {
        "id": str(user["_id"]),
        "email": user["email"],
        "name": user["name"],
        "role": user["role"],
        "permissions": user.get("permissions", []),
        "is_active": user.get("is_active", True),
        "phone": user.get("phone") or None,
        "bio": user.get("bio") or None,
        "has_avatar": bool(user.get("avatar_bytes")),
        "local_password": isinstance(stored_password, str) and stored_password.startswith("$2"),
        "createdAt": user["created_at"],
        "updatedAt": user["updated_at"],
        "last_login": user.get("last_login"),
    }

    if user["role"] == "doctor":
        return DoctorResponse(
            **base_user,
            specialty=user.get("specialty"),
            license_number=user.get("license_number"),
            patients=user.get("patients", []),
            organization_id=user.get("organization_id"),
            schedules=user.get("schedules", []),
            professional_title=user.get("professional_title"),
            department=user.get("department"),
        )
    if user["role"] == "patient":
        return PatientResponse(
            **base_user,
            medical_info=user.get("medical_info", {}),
            practitioners=user.get("practitioners", []),
            health_managers=user.get("health_managers", []),
            rehabilitation_plans=user.get("rehabilitation_plans", []),
            devices=user.get("devices", []),
            emergency_contact=user.get("emergency_contact", {}),
            demographic_info=user.get("demographic_info", {}),
        )
    if user["role"] == "health_manager":
        return HealthManagerResponse(
            **base_user,
            certification=user.get("certification"),
            patients=user.get("patients", []),
            organization_id=user.get("organization_id"),
            schedules=user.get("schedules", []),
            specialty_areas=user.get("specialty_areas", []),
            education=user.get("education", {}),
        )
    if user["role"] == "admin":
        return AdminResponse(
            **base_user,
            admin_level=user.get("admin_level", "regular"),
            managed_organizations=user.get("managed_organizations", []),
        )
    return UserResponse(**base_user)


async def load_user_response(db, user_id: str) -> Optional[UserResponse]:
    """按账号主键读取并映射。畸形 ID 视为不存在，其它读错误原样抛出。"""
    try:
        document = await db.users.find_one({"_id": ObjectId(user_id)})
    except errors.InvalidId:
        return None
    if not document:
        return None
    return user_response_from_document(document)
