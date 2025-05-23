# API routers package 
from app.api.routers.user_router import router as user_router
from app.api.routers.rehabilitation_router import router as rehabilitation_router
from app.api.routers.agent_router import router as agent_router
from app.api.routers.doctor_router import router as doctor_router
from app.api.routers.health_manager_router import router as health_manager_router
from app.api.routers.patient_router import router as patient_router
from app.api.routers.system_admin_router import router as system_admin_router
from app.api.routers.health_alert_router import router as health_alert_router
from app.api.routers.notification_router import router as notification_router
from app.api.routers.device_router import router as device_router
from app.api.routers.device_analysis_router import router as device_analysis_router
from app.api.routers.audit_log_router import router as audit_log_router
from app.api.routers.communication_router import router as communication_router
from app.api.routers.analytics_router import router as analytics_router
# from app.api.routers.auth_router import router as auth_router  # 暂未实现
# from app.api.routers.health_record_router import router as health_record_router  # 暂未实现
# from app.api.routers.device_router import router as device_router  # 设备路由器 - 暂未实现
# from app.api.routers.device_analysis_router import router as device_analysis_router  # 设备分析路由器 - 暂未实现
# from app.api.routers.audit_log_router import router as audit_log_router  # 审计日志路由器 - 已实现 