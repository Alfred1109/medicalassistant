from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Import routers
from app.api.routers import agent_router, rehabilitation_router, user_router
# 导入新增的路由模块
from app.api.routers import doctor_router, health_manager_router, patient_router, system_admin_router, health_alert_router
# 导入数据库连接函数
from app.db.mongodb import connect_to_mongodb, close_mongodb_connection

app = FastAPI(
    title="Medical Rehabilitation Assistant",
    description="A dynamic agent system for medical rehabilitation assistance",
    version="0.1.0",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 添加MongoDB连接和关闭事件
@app.on_event("startup")
async def startup_db_client():
    await connect_to_mongodb()
    
@app.on_event("shutdown")
async def shutdown_db_client():
    await close_mongodb_connection()

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

@app.get("/")
async def root():
    return {"message": "Medical Rehabilitation Assistant API"}

@app.get("/health")
async def health_check():
    return JSONResponse(
        status_code=200,
        content={"status": "healthy"}
    ) 