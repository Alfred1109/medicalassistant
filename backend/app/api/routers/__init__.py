# API routers package 
from app.api.routers.user_router import router as user_router
from app.api.routers.rehabilitation_router import router as rehabilitation_router
from app.api.routers.agent_router import router as agent_router
from app.api.routers.doctor_router import router as doctor_router
from app.api.routers.health_manager_router import router as health_manager_router
from app.api.routers.patient_router import router as patient_router
from app.api.routers.system_admin_router import router as system_admin_router
from app.api.routers.health_alert_router import router as health_alert_router
from app.api.routers.auth_router import router as auth_router
from app.api.routers.health_record_router import router as health_record_router
from app.api.routers.device_router import router as device_router  # 设备路由器
from app.api.routers.device_analysis_router import router as device_analysis_router  # 设备分析路由器 