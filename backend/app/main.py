from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
import time
import uuid

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

# 添加MongoDB连接和关闭事件
@app.on_event("startup")
async def startup_db_client():
    """应用启动时连接数据库"""
    logger.info("Application starting up...")
    try:
        await connect_to_mongodb()
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