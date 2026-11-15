from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
import time
import uuid
from jose import JWTError  # 导入JWTError异常类

# 导入日志模块
from app.core.logging import app_logger as logger
# 导入配置
from app.core.config import settings
# 导入自定义异常类
from app.core.exceptions import AppBaseException
from app.api.router_registry import register_routers
from app.bootstrap import start_background_services, stop_background_services
from app.db.mongodb import connect_to_mongodb, close_mongodb_connection, DatabaseConnectionError
from app.integrations.identity.access import IdentityCsrfMiddleware
from app.core.permission_audit import PermissionAuditMiddleware

# 创建应用实例
from fastapi.staticfiles import StaticFiles
from pathlib import Path as FilePath

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="A dynamic agent system for medical rehabilitation assistance",
    version="0.1.0",
    root_path=settings.MEDICALASSISTANT_ROOT_PATH,
)
_exercise_media = FilePath(__file__).resolve().parents[1] / "data" / "exercise-media"
_exercise_media.mkdir(parents=True, exist_ok=True)
app.mount("/media/exercises", StaticFiles(directory=_exercise_media), name="exercise-media")

# 异常处理中间件
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """请求处理中间件，记录请求信息和处理时间"""
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    
    start_time = time.time()
    logger.info(f"Request started: {request.method} {request.url.path} [ID: {request_id}]")
    
    try:
        response = await call_next(request)
        
        process_time = time.time() - start_time
        logger.info(f"Request completed: {request.method} {request.url.path} - {response.status_code} [{process_time:.4f}s] [ID: {request_id}]")
        
        # 添加处理时间和请求ID到响应头
        response.headers["X-Process-Time"] = str(process_time)
        response.headers["X-Request-ID"] = request_id
        
        return response
    except Exception as e:
        process_time = time.time() - start_time
        logger.error(f"Request failed: {request.method} {request.url.path} - {str(e)} [{process_time:.4f}s] [ID: {request_id}]")
        
        return JSONResponse(
            status_code=500,
            content={
                "error": "INTERNAL_SERVER_ERROR",
                "message": "Internal server error",
                "request_id": request_id
            }
        )

# 权限审计中间件（AUTH02：关键权限操作审计）
# 注册顺序：add_middleware 采用"后注册者在外层"的栈语义，此处必须先于下方
# CORSMiddleware 注册，使审计位于 CORS 之内 —— CORS 预检(OPTIONS)由 CORS
# 直接短路、不会进入审计，且所有响应（含被审计路径）仍携带 CORS 头。
# 审计为旁路记录：身份从 JWT 解出、落库失败仅记日志，不影响业务请求。
app.add_middleware(PermissionAuditMiddleware)
app.add_middleware(IdentityCsrfMiddleware)

# 配置CORS
origins = settings.BACKEND_CORS_ORIGINS
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 添加CORS调试中间件
@app.middleware("http")
async def cors_debug_middleware(request: Request, call_next):
    """CORS调试中间件，记录请求的Origin头"""
    origin = request.headers.get("Origin")
    if origin:
        logger.debug(f"收到请求，Origin: {origin}, 路径: {request.url.path}")
        logger.debug(f"允许的Origins: {origins}")
    
    response = await call_next(request)
    
    if origin:
        cors_headers = {k: v for k, v in response.headers.items() if k.startswith("access-control-")}
        logger.debug(f"返回CORS头: {cors_headers}")
    
    return response


@app.middleware("http")
async def maintenance_gate(request: Request, call_next):
    """Block non-admin API calls while maintenance mode is stored as on."""
    path = request.url.path
    if request.method == "OPTIONS" or not path.startswith("/api/"):
        return await call_next(request)
    if path.startswith("/api/auth") or path.startswith("/api/admin/settings") or path in {"/api/users/login", "/api/users/me"} or path.startswith("/api/users/me/"):
        return await call_next(request)
    try:
        from app.db.mongodb import db as mongo
        if not mongo.is_connected():
            return await call_next(request)
        database = mongo.db
        row = await database.system_settings.find_one({"_id": "system"})
        if not row or not row.get("maintenance_mode"):
            return await call_next(request)
        from app.core.auth import request_actor_role
        role = await request_actor_role(request, database)
    except Exception:
        return await call_next(request)
    if role == "admin":
        return await call_next(request)
    return JSONResponse(status_code=503, content={"code": "MAINTENANCE", "message": "系统正在维护，请稍后再试。"})


# 添加MongoDB连接和关闭事件
@app.on_event("startup")
async def startup_db_client():
    """应用启动时连接数据库，再拉起后台服务。"""
    logger.info("Application starting up...")
    try:
        await connect_to_mongodb()
        await start_background_services(app)
    except DatabaseConnectionError as e:
        logger.critical(f"Failed to connect to database: {str(e)}")
        # 不启动无法访问数据库的服务。
        raise

@app.on_event("shutdown")
async def shutdown_db_client():
    """应用关闭时先停后台服务，再断开数据库连接"""
    logger.info("Application shutting down...")
    await stop_background_services()
    await close_mongodb_connection()

# 自定义异常处理
@app.exception_handler(AppBaseException)
async def app_exception_handler(request: Request, exc: AppBaseException):
    """处理应用自定义异常"""
    logger.warning(
        f"AppException: {exc.error_code} - {exc.message} - {request.method} {request.url.path}",
        extra={"details": exc.details}
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.error_code,
            "message": exc.message,
            "details": exc.details,
            "request_id": getattr(request.state, "request_id", str(uuid.uuid4()))
        }
    )

# 添加JWT异常处理
@app.exception_handler(JWTError)
async def jwt_exception_handler(request: Request, exc: JWTError):
    """处理JWT令牌验证异常"""
    logger.warning(f"JWT验证错误: {str(exc)} - {request.method} {request.url.path}")
    
    return JSONResponse(
        status_code=401,
        content={
            "error": "INVALID_TOKEN",
            "message": "无效的认证令牌",
            "details": {"reason": str(exc)},
            "request_id": getattr(request.state, "request_id", str(uuid.uuid4()))
        },
        headers={"WWW-Authenticate": "Bearer"}
    )

# 验证错误处理
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """处理请求验证错误"""
    errors = exc.errors()
    error_details = []
    
    for error in errors:
        error_details.append({
            "loc": error.get("loc", []),
            "msg": error.get("msg", ""),
            "type": error.get("type", "")
        })
    
    logger.warning(f"Validation error: {request.method} {request.url.path} - {error_details}")
    
    return JSONResponse(
        status_code=422,
        content={
            "error": "VALIDATION_ERROR",
            "message": "Validation Error",
            "details": {"errors": error_details},
            "request_id": getattr(request.state, "request_id", str(uuid.uuid4()))
        }
    )

register_routers(app)

@app.get("/api")
async def api_root():
    """API根路径响应"""
    logger.debug("API root endpoint called")
    return {
        "name": settings.PROJECT_NAME,
        "version": settings.API_VERSION,
        "status": "running",
        "docs_url": "/docs",
        "health_url": "/health"
    }

@app.get("/")
async def root():
    """API根路径响应"""
    logger.debug("Root endpoint called")
    return {"message": f"Welcome to {settings.PROJECT_NAME} API"}

@app.get("/health")
async def health_check():
    """健康检查端点"""
    from app.schemas.common import HealthCheck
    from app.db.mongodb import db
    import platform
    import sys
    
    logger.debug("Health check endpoint called")
    
    # 创建健康检查响应
    health_response = {
        "status": "healthy",
        "components": {
            "system": {
                "python_version": sys.version,
                "platform": platform.platform()
            },
            "api": {
                "status": "running"
            }
        }
    }
    
    # 检查数据库连接
    if settings.HEALTH_CHECK_INCLUDE_DB:
        try:
            db_status = await db.ping()
            health_response["components"]["database"] = {
                "status": "connected" if db_status else "disconnected",
                "type": "MongoDB"
            }
            
            if not db_status:
                health_response["status"] = "degraded"
        except Exception as e:
            logger.error(f"Health check - Database error: {str(e)}")
            health_response["components"]["database"] = {
                "status": "error",
                "error": str(e),
                "type": "MongoDB"
            }
            health_response["status"] = "degraded"
    
    # 缓存状态
    from app.core.cache import cache
    health_response["components"]["cache"] = {
        "status": "enabled" if settings.CACHE_ENABLED else "disabled",
        "size": cache.size() if settings.CACHE_ENABLED else 0
    }
    
    # 创建健康检查响应对象
    health = HealthCheck(**health_response)
    
    return JSONResponse(
        status_code=200 if health.status == "healthy" else 207,
        content=health.model_dump(mode="json")
    )
