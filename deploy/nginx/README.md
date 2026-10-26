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

改前缀时,这两处必须一起改,否则前端会 404:

1. `frontend/.env.local` 的 `VITE_API_PREFIX`
2. `/etc/nginx/sites-available/diaochawenjuan` 里的 `location` 路径与 `rewrite` 正则

`frontend/vite.config.ts` 的 `base` 会自动跟随 `VITE_API_PREFIX`,不用手动改。

安装/更新 nginx 配置:

```bash
sudo cp deploy/nginx/diaochawenjuan.conf /etc/nginx/sites-available/diaochawenjuan
sudo nginx -t && sudo systemctl reload nginx
```

## 启动

```bash
# MongoDB
sudo systemctl start mongod

# 后端(5502)
cd backend && ./venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 5502

# 前端(5501)
cd frontend && npm run dev
```

后端依赖 `backend/venv`(已建),前端依赖 `frontend/node_modules`(已装)。

> 注意:项目自带的 `start-project.sh` 用的是 `--host 0.0.0.0`,会把后端暴露到局域网。
> 走 nginx 统一入口时建议改用 `127.0.0.1`。

## 默认账号

| 角色 | 账号 | 密码 |
|---|---|---|
| 管理员 | admin@example.com | Admin123! |
| 医生 | doctor@example.com | Doctor123! |
| 健康管理师 | liujk@example.com | Manager123! |
| 患者 | zhangsan@example.com | Patient123! |
| 测试 | test@example.com | password123 |

## 已知问题

- `npm run build` 目前跑不通:`tsc` 阶段有约 1210 个既有类型错误,主要来自
  `frontend/src/types/index.d.ts` 里手写的类型桩遮蔽了真实的 `@mui/material`、`axios`、
  `react-router-dom`。Vite dev server 不做类型检查,所以开发模式不受影响。
  修桩之前不要把 `tsc &&` 从 build 脚本里摘掉 —— 那是掩盖问题,不是修复。
- `frontend/src/components/Agent/AgentForm.tsx` 开头原本有两个全角标点 `。、`,
  会让 tsc 报语法错误并**跳过全部语义检查**,从而掩盖上面那批类型错误。已修正。
