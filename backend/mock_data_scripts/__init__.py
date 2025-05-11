"""
模拟数据生成脚本包

此包包含所有用于生成系统模拟数据的脚本，用于开发和测试阶段初始化数据库。
主要功能包括：
- 生成用户数据（管理员、医生、健康管理师、患者）
- 生成医疗机构数据
- 生成健康记录数据
- 生成康复计划数据
- 生成设备数据和测量数据
- 生成仪表盘数据和通知数据

使用方法：
```
python -m mock_data_scripts.create_mockdata
```
"""

__all__ = [
    'create_mockdata',
    'create_test_users',
    'create_test_doctors',
    'create_test_patients',
    'create_test_health_managers',
    'create_test_rehab_plans',
    'create_test_health_records', 
    'create_test_devices',
    'create_test_organizations',
    'init_dashboard_data',
    'init_notification_data',
    'update_test_patients'
]
