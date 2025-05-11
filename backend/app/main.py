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

# Import routers
from app.api.routers import agent_router, rehabilitation_router, user_router
# 导入新增的路由模块
from app.api.routers import doctor_router, health_manager_router, patient_router, system_admin_router, health_alert_router, notification_router
# 导入数据库连接函数
from app.db.mongodb import connect_to_mongodb, close_mongodb_connection, DatabaseConnectionError

# 导入WebSocket服务
from app.api.websockets import setup_websockets
# 导入通信路由
from app.api.routers import communication_router

# 添加新的路由导入
from .api.routers import report_scheduler_router, data_filter_router

# 导入设备相关路由
from .api.routers.device_router import router as device_router
from .api.routers.device_repair_router import router as device_repair_router
from .api.routers.device_data_standard_router import router as device_data_standard_router

# 导入权限审计中间件
# from app.core.permission_audit import PermissionAuditMiddleware

# 创建应用实例
app = FastAPI(
    title=settings.PROJECT_NAME,
    description="A dynamic agent system for medical rehabilitation assistance",
    version="0.1.0",
)

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

# 添加MongoDB连接和关闭事件
@app.on_event("startup")
async def startup_db_client():
    """应用启动时连接数据库"""
    logger.info("Application starting up...")
    try:
        await connect_to_mongodb()
        
        # 初始化用户服务，确保创建默认用户
        from app.services.user_service import UserService
        from app.db.mongodb import db
        user_service = UserService(db.db)
        await user_service.initialize()
        logger.info("用户服务初始化完成，已创建默认用户")
        
        # 初始化WebSocket服务
        setup_websockets(app)
        logger.info("WebSocket服务已初始化")
    except DatabaseConnectionError as e:
        logger.critical(f"Failed to connect to database: {str(e)}")
        # 在生产环境可能需要退出应用
        # import sys
        # sys.exit(1)
    
@app.on_event("shutdown")
async def shutdown_db_client():
    """应用关闭时断开数据库连接"""
    logger.info("Application shutting down...")
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

# Include routers
app.include_router(user_router, prefix="/api/users", tags=["users"])
app.include_router(rehabilitation_router, prefix="/api/rehabilitation", tags=["rehabilitation"])
app.include_router(agent_router, prefix="/api/agents", tags=["agent"])

# 新增角色和功能相关路由
app.include_router(doctor_router, prefix="/api/doctors", tags=["doctors"])
app.include_router(health_manager_router, prefix="/api/health-managers", tags=["health-managers"])
app.include_router(patient_router, prefix="/api/patients", tags=["patients"])
app.include_router(system_admin_router, prefix="/api/admin", tags=["admin"])
# 健康预警路由
app.include_router(health_alert_router, tags=["health-alerts"])
# 添加通知路由
app.include_router(notification_router, prefix="/api", tags=["notifications"])

# 注册通信路由
app.include_router(communication_router, prefix="/api", tags=["communications"])

# 在 app.include_router 部分添加新的路由
app.include_router(report_scheduler_router.router, prefix="/api")
app.include_router(data_filter_router.router, prefix="/api")

# 添加设备相关路由
app.include_router(device_router, prefix="/api")
app.include_router(device_repair_router, prefix="/api")
app.include_router(device_data_standard_router, prefix="/api")

# 添加审计日志路由
from app.api.routers import audit_log_router
app.include_router(audit_log_router, prefix="/api", tags=["audit-logs"])

# 添加数据分析路由
from app.api.routers import analytics_router
app.include_router(analytics_router, prefix="/api", tags=["analytics"])

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