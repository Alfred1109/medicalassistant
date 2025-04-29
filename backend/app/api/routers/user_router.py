from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Dict, Any, Optional
from fastapi.security import OAuth2PasswordRequestForm

from app.schemas.user import UserCreate, UserUpdate, UserResponse, UserLogin, Token, PermissionAssignment
from app.services.user_service import UserService
from app.core.dependencies import get_user_service, get_current_user
from app.core.permissions import require_permission, Permission, PermissionChecker

router = APIRouter()

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_user(
    user_data: UserCreate,
    user_service: UserService = Depends(get_user_service)
):
    """注册新用户(仅限患者自注册)"""
    # 限制只能创建患者类型的用户
    if user_data.role != "patient":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只能注册患者用户，其他类型用户需要管理员创建"
        )
    return await user_service.create_user(user_data)

@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    user_service: UserService = Depends(get_user_service)
):
    """用户登录并获取访问令牌"""
    try:
        user = await user_service.authenticate_user(form_data.username, form_data.password)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户名或密码不正确",
                headers={"WWW-Authenticate": "Bearer"},
            )
        token = await user_service.create_token(user)
        return token
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: UserResponse = Depends(get_current_user)
):
    """获取当前登录用户信息"""
    return current_user

@router.put("/me", response_model=UserResponse)
async def update_current_user(
    user_data: UserUpdate,
    current_user: UserResponse = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service)
):
    """更新当前登录用户信息"""
    # 不允许自己修改角色和权限
    if user_data.role is not None or user_data.permissions is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="不能修改自己的角色或权限"
        )
    return await user_service.update_user(current_user.id, user_data)

@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    user_service: UserService = Depends(get_user_service),
    current_user: UserResponse = Depends(get_current_user),
    _: None = Depends(require_permission(Permission.USER_READ))
):
    """根据ID获取用户信息(需要权限)"""
    user = await user_service.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return user

@router.get("/", response_model=List[UserResponse])
async def list_users(
    role: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    user_service: UserService = Depends(get_user_service),
    current_user: UserResponse = Depends(get_current_user),
    _: None = Depends(require_permission(Permission.USER_READ))
):
    """列出用户(可按角色筛选)"""
    return await user_service.list_users(role, skip, limit)

@router.post("/create", response_model=UserResponse)
async def create_user(
    user_data: UserCreate,
    user_service: UserService = Depends(get_user_service),
    current_user: UserResponse = Depends(get_current_user),
    _: None = Depends(require_permission(Permission.USER_CREATE))
):
    """创建新用户(管理员权限)"""
    return await user_service.create_user(user_data)

@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    user_data: UserUpdate,
    user_service: UserService = Depends(get_user_service),
    current_user: UserResponse = Depends(get_current_user),
    _: None = Depends(require_permission(Permission.USER_UPDATE))
):
    """更新用户信息(需要权限)"""
    user = await user_service.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
        
    # 如果非管理员尝试修改他人为管理员，禁止操作
    if user_data.role == "admin" and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有管理员可以创建或修改管理员账户"
        )
        
    return await user_service.update_user(user_id, user_data)

@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: str,
    user_service: UserService = Depends(get_user_service),
    current_user: UserResponse = Depends(get_current_user),
    _: None = Depends(require_permission(Permission.USER_DELETE))
):
    """删除用户(需要权限)"""
    # 实际上只是停用账号，不真正删除数据
    result = await user_service.deactivate_user(user_id)
    if not result:
        raise HTTPException(status_code=404, detail="用户不存在")
    return None

@router.post("/permissions", response_model=UserResponse)
async def update_user_permissions(
    permission_data: PermissionAssignment,
    user_service: UserService = Depends(get_user_service),
    current_user: UserResponse = Depends(get_current_user),
    _: None = Depends(require_permission(Permission.USER_UPDATE))
):
    """更新用户权限(需要管理员权限)"""
    # 检查更新者权限
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有管理员可以修改用户权限"
        )
        
    # 更新权限
    user = await user_service.update_user_permissions(
        permission_data.user_id, 
        permission_data.permissions
    )
    
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return user

@router.post("/activate/{user_id}", response_model=UserResponse)
async def activate_user(
    user_id: str,
    user_service: UserService = Depends(get_user_service),
    current_user: UserResponse = Depends(get_current_user),
    _: None = Depends(require_permission(Permission.USER_UPDATE))
):
    """激活已停用的用户账户(需要管理员权限)"""
    await user_service.activate_user(user_id)
    user = await user_service.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return user

@router.post("/patients/{patient_id}/practitioners", response_model=UserResponse)
async def assign_practitioner(
    patient_id: str,
    practitioner_id: str,
    user_service: UserService = Depends(get_user_service),
    current_user: UserResponse = Depends(get_current_user),
    _: None = Depends(require_permission(Permission.PATIENT_UPDATE))
):
    """为患者分配医生/健康管理师"""
    result = await user_service.assign_practitioner(patient_id, practitioner_id)
    if not result:
        raise HTTPException(status_code=404, detail="患者或医疗人员不存在")
    return result

@router.delete("/patients/{patient_id}/practitioners/{practitioner_id}", response_model=UserResponse)
async def remove_practitioner(
    patient_id: str,
    practitioner_id: str,
    user_service: UserService = Depends(get_user_service),
    current_user: UserResponse = Depends(get_current_user),
    _: None = Depends(require_permission(Permission.PATIENT_UPDATE))
):
    """移除患者的医生/健康管理师关联"""
    result = await user_service.remove_practitioner(patient_id, practitioner_id)
    if not result:
        raise HTTPException(status_code=404, detail="患者或医疗人员不存在")
    return result 