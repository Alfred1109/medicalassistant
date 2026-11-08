# OIDC 授权码与 PKCE 隔离实验

本目录是协议技术验证，不会给两个应用的正式 factory 注册 OIDC 路由，也未接通 Rehabman 的 FastAPI 认证依赖。提供方加载真实问卷应用、真实 `User` 模型和 `/auth/login`，仅使用每轮新建的 SM4 SQLite 合成库、新密钥及合成普通用户；依赖保存在私有 `.deps`，没有改动原有虚拟环境。

固定本地 issuer 为 `http://127.0.0.1:15512`，实验 RP 为 `http://127.0.0.1:15513`，唯一回调为 `/auth/oidc/callback`。Authlib 处理授权码、S256 PKCE、state、nonce、RS256 ID Token 和 JWKS。两端实验会话均在进程内服务端保存，Cookie 只有随机会话 ID；没有把源令牌存入 localStorage 或浏览器 Cookie。访问日志删除查询串，避免记录授权码等材料。

## 复现

依赖先按问卷仓库自己的锁文件配置其 `venv` 和 SM4 SQLite 驱动。默认源仓库为本项目相邻的 `康复问卷管理系统`，可用 `QUESTIONNAIRE_ROOT` 指定。实验使用 source venv 的 Python 及既有应用依赖，新增协议包按本目录 `requirements.lock` 安装到私有目录：

```bash
./experiments/oidc-pilot/install.sh
```

HTTP 正反例验证（执行后自动停止线程并删除该轮数据库和密钥）：

```bash
"../康复问卷管理系统/venv/bin/python" experiments/oidc-pilot/verify.py
```

浏览器人工验证使用独立启停脚本：

```bash
./experiments/oidc-pilot/start.sh
# 打开 http://127.0.0.1:15513/auth/oidc/start
# 本轮合成凭据仅在 .runtime/run-*/synthetic-credentials.json
./experiments/oidc-pilot/stop.sh
```

`start.sh` 每次拒绝复用旧数据库，端口被占用就失败，不终止占用者。`.runtime` 下的密钥、数据库、合成凭据和 `.deps` 全部在局部 `.gitignore` 中；完成后在核实本轮进程已停止的情况下清理本轮 runtime。实验只绑定回环地址；不要发布、反向代理或用于真实用户。

## 2026-11-08 验证结果

真实本地 HTTP 链路 9 项通过：源密码登录、授权码/S256 登录、没有临床权限、回调重放拒绝、错误 state 拒绝、错误 nonce 拒绝、错误 PKCE 拒绝、授权码重放拒绝、源账号停用后换取 token 拒绝。

真实 Chromium 浏览器从 RP 跳转到源 `/auth/login`，输入合成凭据及实际图形验证码，登录后返回 RP `/auth/session`，显示 `authenticated=true`、匹配 issuer、空 `clinical_permissions`；访问 `/clinical/patients` 返回 HTTP 403。截图为项目 `output/playwright/oidc-pilot-session.png`。浏览器此轮没有调用固定验证码夹具。

源代码基线 HEAD：`1b01f065ef9e874fca5126ecc1464702679e024a`，另有本轮既存未提交 integration Grant 改动；源 `requirements.lock` SHA-256：`f2b0a7c6986de4a4a039af91c71ba857fe8131481011421e00aec1a1613eaa0c`。运行环境 Python 3.11.15、Flask 3.1.3、Flask-SQLAlchemy 3.1.1、Authlib 1.9.5。当前源环境的 chardet 版本使 Requests 发出依赖警告，Authlib 还发出 grant hook 弃用警告；不据此宣称正式依赖组合已验收。

## 验证边界

- 全部为 loopback HTTP，实验仅为该进程显式允许非 TLS；没有验证正式 HTTPS、Cookie Secure、真实域名、跨站 iframe、Safari 或生产反向代理。
- HTTP 自动化为验证码创建固定挑战测试夹具；真实 `/auth/login` 仍校验 CSRF、验证码挑战、密码和启用状态。该辅助路由只存在于实验实例，不代表图形验证码防自动化验收。
- 使用源 testing 配置和普通合成用户，未验证 MFA、医护申请审核、患者核实、全局退出和授权撤销时限。
- 固定预登记实验客户端自动许可 `openid profile`，没有用户授权同意界面。ID Token 只确认身份；实验不授医护角色、患者数据、中心或临床动作权限。
- RP 是独立 Flask 协议实验客户端；未将实验登录结果注入现有 FastAPI/JWT、真实身份投影或旧账号映射。
- 授权码及客户端模型仅为实验；密钥轮换、授权码并发消费、持久化会话、正式客户端注册管理、授权内省与撤权仍须正式实现和验证。

官方接口依据：[Flask OIDC Provider](https://docs.authlib.org/en/stable/oauth2/authorization-server/flask/openid-connect.html)、[Web Clients](https://docs.authlib.org/en/stable/oauth2/client/web/)、[PKCE HTTP client](https://docs.authlib.org/en/stable/oauth2/client/http/index.html)。
