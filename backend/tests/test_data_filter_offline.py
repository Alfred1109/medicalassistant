"""T79 语义锁定：data_filter 整体下线。

data_filter_router 对任意 MongoDB 集合做原生条件查询透传（仅校验集合存在，
无集合白名单、无角色限制、无对象级访问控制、支持任意 projection），任何登录
用户可绕过各业务域的对象级授权读取任意集合（含患者数据、users、account_fences）。

处置决策（T79，参照 T53 死代码处置先例）：git 溯源该路由自仓库起源提交
dac0330（2025-05-10，"update"）随脚手架批量引入，前端零引用、docs 仅存旧
脚手架完成度宣传与 wp0 盘点「待核实」登记，无任何业务消费方——整体删除路由
与服务，不做白名单收口。
"""
import unittest
from importlib import import_module

from app.main import app


class DataFilterOfflineTests(unittest.TestCase):
    def test_data_filter_router_module_no_longer_importable(self):
        with self.assertRaises(ModuleNotFoundError):
            import_module("app.api.routers.data_filter_router")
        with self.assertRaises(ModuleNotFoundError):
            import_module("app.services.data_filter_service")

    def test_no_data_filter_routes_mounted(self):
        paths = {route.path for route in app.routes}
        leaked = [path for path in paths if "/data-filters" in path]
        self.assertEqual(leaked, [])

    def test_data_filter_endpoints_return_404(self):
        for path in ("/api/data-filters", "/api/data-filters/apply",
                     "/api/data-filters/save", "/api/data-filters/schema/users"):
            with self.subTest(path=path):
                self.assertIsNone(
                    next((route for route in app.routes
                          if getattr(route, "path", None) == path), None),
                    f"下线路由仍挂载: {path}")


if __name__ == "__main__":
    unittest.main()
