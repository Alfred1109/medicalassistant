#!/usr/bin/env python3
"""
模拟数据生成脚本运行器

此脚本提供命令行界面，用于运行各种模拟数据生成脚本。
可以生成全部数据或指定特定类型的数据。
"""
import os
import sys
import argparse
import asyncio
import importlib
from pathlib import Path

# 添加项目根目录到系统路径
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

# 可用的模拟数据生成脚本
AVAILABLE_SCRIPTS = {
    "all": "create_mockdata",
    "users": "create_test_users",
    "doctors": "create_test_doctors",
    "patients": "create_test_patients",
    "health_managers": "create_test_health_managers",
    "rehab_plans": "create_test_rehab_plans",
    "health_records": "create_test_health_records",
    "devices": "create_test_devices",
    "organizations": "create_test_organizations",
    "dashboard": "init_dashboard_data",
    "notifications": "init_notification_data",
    "update_patients": "update_test_patients"
}

def print_available_scripts():
    """打印可用的模拟数据生成脚本"""
    print("\n可用的模拟数据生成选项:")
    print("-" * 30)
    print(f"  all           - 生成所有模拟数据")
    print(f"  users         - 生成基础用户账号")
    print(f"  organizations - 生成医疗机构数据")
    print(f"  doctors       - 生成医生数据")
    print(f"  health_managers - 生成健康管理师数据")
    print(f"  patients      - 生成患者数据")
    print(f"  rehab_plans   - 生成康复计划数据")
    print(f"  health_records - 生成健康记录数据")
    print(f"  devices       - 生成设备和设备数据")
    print(f"  dashboard     - 生成仪表盘数据")
    print(f"  notifications - 生成通知数据")
    print(f"  update_patients - 更新患者数据")

def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="医疗康复助手模拟数据生成工具")
    parser.add_argument(
        "data_type", nargs="?", default="all",
        help="要生成的数据类型 (默认: all，生成所有数据)"
    )
    parser.add_argument(
        "--list", "-l", action="store_true",
        help="列出所有可用的数据类型"
    )
    parser.add_argument(
        "--force", "-f", action="store_true",
        help="强制重新生成数据，不进行确认提示"
    )
    
    args = parser.parse_args()
    
    if args.list:
        print_available_scripts()
        sys.exit(0)
    
    if args.data_type not in AVAILABLE_SCRIPTS:
        print(f"错误: 未知的数据类型 '{args.data_type}'")
        print_available_scripts()
        sys.exit(1)
    
    return args

async def run_script(script_name):
    """运行指定的模拟数据生成脚本"""
    try:
        # 动态导入模块
        module_path = f"mock_data_scripts.{script_name}"
        module = importlib.import_module(module_path)
        
        # 查找主函数（通常是create_test_*或init_*）
        main_function = None
        for name in dir(module):
            if name.startswith(("create_", "init_")):
                main_function = getattr(module, name)
                break
        
        if main_function is None:
            print(f"错误: 在 {script_name} 中未找到主函数")
            return False
        
        # 运行主函数
        print(f"\n运行 {script_name}...")
        if asyncio.iscoroutinefunction(main_function):
            await main_function()
        else:
            main_function()
        
        return True
    except ImportError as e:
        print(f"错误: 无法导入模块 {script_name}")
        print(f"详细信息: {e}")
        return False
    except Exception as e:
        print(f"错误: 运行 {script_name} 时出错")
        print(f"详细信息: {e}")
        return False

async def main():
    """主函数"""
    args = parse_args()
    
    script_name = AVAILABLE_SCRIPTS[args.data_type]
    
    # 确认提示
    if not args.force and args.data_type == "all":
        confirm = input("\n警告: 即将生成所有模拟数据，这可能需要一些时间并且会修改数据库内容。确定要继续吗? (y/N): ").lower()
        if confirm != "y":
            print("已取消操作")
            return
    
    print("\n" + "=" * 50)
    print(f"开始生成{args.data_type}模拟数据")
    print("=" * 50)
    
    if args.data_type == "all":
        success = await run_script(script_name)
    else:
        success = await run_script(script_name)
    
    if success:
        print("\n" + "=" * 50)
        print(f"{args.data_type}模拟数据生成完成!")
        print("=" * 50)
    else:
        print("\n" + "=" * 50)
        print(f"{args.data_type}模拟数据生成失败!")
        print("=" * 50)
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main()) 