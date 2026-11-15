"""HTTP 路由注册表。顺序与历史 main.include_router 调用一致。"""


def register_routers(app) -> None:
    from app.api.routers import (
        agent_router, analytics_router, audit_log_router, communication_router,
        doctor_router, health_alert_router, health_manager_router, health_record_router,
        notification_router, patient_router, rehabilitation_router, system_admin_router,
        user_router,
    )
    from app.api.routers.device_analysis_router import router as device_analysis_router
    from app.api.routers.device_data_standard_router import router as device_data_standard_router
    from app.api.routers.device_repair_router import router as device_repair_router
    from app.api.routers.device_router import router as device_router
    from app.api.routers.followup_reminder_router import router as followup_reminder_router
    from app.api.routers.icf_router import router as icf_router
    from app.api.routers.patient_account_binding_router import router as patient_account_binding_router
    from app.api.routers.quality_issue_router import router as quality_issue_router
    from app.api.routers.quality_monitoring_router import router as quality_monitoring_router
    from app.api.routers.rehab_feedback_router import router as rehab_feedback_router
    from app.api.routers.rehab_publication_router import router as rehab_publication_router
    from app.api.routers import report_scheduler_router
    from app.clinical.router import router as clinical_router
    from app.directory.router import router as directory_router
    from app.integrations.forms.catalog_router import router as form_catalog_router
    from app.integrations.forms.form_bindings import router as form_bindings_router
    from app.integrations.forms.patient_links import router as form_patient_links_router
    from app.integrations.forms.router import router as integration_forms_router
    from app.integrations.identity.router import router as identity_router

    app.include_router(user_router, prefix="/api/users", tags=["users"])
    app.include_router(rehabilitation_router, prefix="/api/rehabilitation", tags=["rehabilitation"])
    app.include_router(agent_router, prefix="/api/agents", tags=["agent"])
    app.include_router(doctor_router, prefix="/api/doctors", tags=["doctors"])
    app.include_router(health_manager_router, prefix="/api/health-managers", tags=["health-managers"])
    app.include_router(patient_router, prefix="/api/patients", tags=["patients"])
    app.include_router(patient_account_binding_router, prefix="/api", tags=["patient-account-bindings"])
    app.include_router(system_admin_router, prefix="/api/admin", tags=["admin"])
    app.include_router(followup_reminder_router, prefix="/api")
    app.include_router(rehab_publication_router, prefix="/api")
    app.include_router(rehab_feedback_router, prefix="/api")
    app.include_router(quality_monitoring_router, prefix="/api")
    app.include_router(quality_issue_router, prefix="/api")
    app.include_router(health_record_router, prefix="/api")
    app.include_router(health_alert_router, tags=["health-alerts"])
    app.include_router(notification_router, prefix="/api", tags=["notifications"])
    app.include_router(communication_router, prefix="/api", tags=["communications"])
    app.include_router(report_scheduler_router.router, prefix="/api")
    app.include_router(device_router, prefix="/api")
    app.include_router(device_analysis_router, prefix="/api")
    app.include_router(device_repair_router, prefix="/api")
    app.include_router(device_data_standard_router, prefix="/api")
    app.include_router(audit_log_router, prefix="/api", tags=["audit-logs"])
    app.include_router(analytics_router, prefix="/api", tags=["analytics"])
    app.include_router(integration_forms_router, prefix="/api", tags=["form-integration"])
    app.include_router(form_catalog_router, prefix="/api")
    app.include_router(form_patient_links_router, prefix="/api")
    app.include_router(form_bindings_router, prefix="/api")
    app.include_router(identity_router, prefix="/api")
    app.include_router(clinical_router, prefix="/api")
    app.include_router(directory_router, prefix="/api")
    app.include_router(icf_router, prefix="/api", tags=["icf"])
