# medicalassistant 部署说明

本项目以 `/medical` 为路径前缀,与同机的 newcrf(Flask,根路径 `/`)共存于 nginx :80。

## 访问地址

| 路径 | 目标 | 说明 |
|---|---|---|
| `/medical/` | `127.0.0.1:5501` | 前端 Vite dev server(base 为 `/medical/`) |
| `/medical/api/*` | `127.0.0.1:5502` | 后端 FastAPI,`/medical` 前缀被剥掉 |
| `/medical/ws/*` | `127.0.0.1:5502` | WebSocket,后端路由 `/ws/chat/{conversation_id}` |
| `/medical/docs` | `127.0.0.1:5502` | FastAPI 自带的 Swagger UI |
| `/medical/openapi.json` | `127.0.0.1:5502` | OpenAPI schema |
| `/` | `127.0.0.1:5001` | newcrf(Flask),未改动 |
| `/kf/` | `127.0.0.1:6001` | ZL-kfqb,未改动 |

## 配置同步点

改前缀时,这三处必须一起改,否则前端、后端重定向或文档地址会丢前缀:

1. `frontend/.env.local` 的 `VITE_API_PREFIX`
2. `/etc/nginx/sites-available/diaochawenjuan` 里的 `location` 路径与 `rewrite` 正则
3. 后端服务环境 `MEDICALASSISTANT_ROOT_PATH=/medical`，对应 FastAPI 的受控 ASGI root_path

`frontend/vite.config.ts` 的 `base` 会自动跟随 `VITE_API_PREFIX`,不用手动改。

安装/更新 nginx 配置:

```bash
sudo cp deploy/nginx/diaochawenjuan.conf /etc/nginx/sites-available/diaochawenjuan
sudo nginx -t && sudo systemctl reload nginx
```

## 启动

```bash
# 先配置并独立启动 MongoDB，副本集说明见 ../mongodb/README.md
# 检查本项目依赖、数据库和端口
DEBUG=false ./start.sh --check
# 经 nginx 访问时，前后端监听回环地址
DEBUG=false MEDICALASSISTANT_HOST=127.0.0.1 MEDICALASSISTANT_ROOT_PATH=/medical ./start.sh
# 状态与停止
./start.sh --status
./stop.sh
```

脚本使用项目内 `backend/.venv` 或 `backend/venv`，前端依赖 `frontend/node_modules`；缺失依赖明确报错，不自动安装或管理 MongoDB。数据库与应用分别管理，事务相关功能要求副本集，见 [MongoDB 说明](../mongodb/README.md)。

后端依赖须完整安装 `backend/requirements.txt`；其中明确固定了 `websockets==12.0`。单独安装基础 `uvicorn` 只能保证 HTTP，可能没有 WebSocket 协议。启动预检会导入所选后端 Python 的实际 WebSocket 实现，启动命令也显式选择 `--ws websockets`；缺失或不兼容时直接报错，避免 HTTP 健康正常但聊天/通知升级失败。

根路径部署保持 `MEDICALASSISTANT_ROOT_PATH` 为空。该配置只影响公开 URL、尾斜杠重定向和文档地址，后端仍接收已剥前缀的 `/api/*`、`/ws/*` 和 `/docs`；不要再把 `/medical` 加入路由。后端不信任客户端提供的 `X-Forwarded-Prefix`。代理还应保留公开 Host（非标准端口时含端口），由受信本机代理传递 HTTPS scheme；仅在 Uvicorn 明确信任的代理地址上接受转发头。统一登录的 `OIDC_PUBLIC_BASE_URL` 路径也必须使用同一前缀。线上现有服务需要在其私有环境文件中显式设置该值并按发布流程重启才会生效，本地文档更新不代表现网已改。


## 账号与验证

普通启动不创建默认演示账号。仅在明确的本地隔离测试库中按 [隔离演示说明](../../docs/isolated-demo-accounts.md) 初始化合成账号；既有或正式账号通过对应身份管理流程处理。当前构建、联调及尚未完成的统一身份边界以 [开发计划](../../docs/development-plan-2026-11-07.md) 的证据记录为准，nginx 可访问不代表业务验收完成。
