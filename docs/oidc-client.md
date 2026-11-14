# OIDC 客户端接入与核实绑定

本模块默认关闭。统一模式使用 113.44 验证身份，管理员逐个核实绑定后保留康复系统原有 actor、角色和对象授权。源端研究角色、同名账号或单纯 OIDC 身份声明不会获得康复权限。实验目录不用于生产；本地实现与隔离测试不代表现网已切换。

> 2026-11-14 复核：源端（113.44 问卷系统）技术栈为 Flask + SQLAlchemy + SQLite（可选 SM4 字段加密），不是 FastAPI；部署为 gunicorn workers=1、nginx TLS 终结，`TRUSTED_PROXY_HOPS` 必须配置。下文「填报身份委托」所述的显式一对一配对与操作人解析已在源端实现并有测试。两端均为本地实现，未做真实 provider/RP 与浏览器全链路验收，本文不宣称跨端闭环已完成。

启用配置 `OIDC_ENABLED=true`、`OIDC_ISSUER`、`OIDC_CLIENT_ID`、`OIDC_CLIENT_SECRET`、`OIDC_PUBLIC_BASE_URL` 和独立持久 `OIDC_SESSION_ENCRYPTION_KEY`（Fernet 32 字节密钥的 urlsafe-base64 编码）。密钥保存在服务端私有配置，不进 Git。两项 URL 必须是精确 HTTPS 地址且末尾无 `/`；例如公开根可为 `https://care.example/medical`，预登记回调必须精确为 `https://care.example/medical/api/auth/oidc/callback`。配置不允许公开 HTTP 豁免。后端可在受控 Nginx 后运行 HTTP，浏览器入口与身份提供方对外连接仍需可信 TLS。

`OIDC_AUTHENTICATION_MODE=legacy` 为默认值，保留原认证；此时 OIDC 只进行身份验证，不进入业务依赖。明确切到 `oidc` 后，所有业务 HTTP/WS 使用服务器会话，旧 JWT、密码登录/注册/刷新路由与服务签发入口均拒绝，源不可用不会回退旧身份。部署切换必须同时交付对应前端和源状态接口。

`GET /api/auth/oidc/start` 发起顶层授权码 + S256 PKCE；state、nonce、verifier 保存在 Mongo 服务端，回调一次原子消费。使用 Authlib OAuth 客户端与 OIDC claims 校验、joserfc RS256/JWKS 验签。发现文档固定 issuer，并将端点限制在该 HTTPS 源；不跟随远端重定向。启用时 TTL/唯一索引失败会阻止启动，不降级为非原子内存状态。

浏览器只接收随机 `__Host-` Secure/HttpOnly/SameSite=Lax 会话 Cookie，敏感响应 no-store、no-referrer。源 access token 经独立 Fernet 密钥加密保存在服务端，用于每次调用固定 `/oidc/introspect`；不保存 ID/刷新令牌，也不把令牌返回浏览器。每次检查 source issuer、client、subject、有效期和 active；源停用/改密/退出由源的凭据版本判定为失效后，本地销毁旧会话。源网络失败返回 503，不能按旧缓存或 JWT 放行。

应用会话有效期取 OIDC 配置、运营会话时限和源 access token 实际有效期的最短值，限制同时写入服务器会话及浏览器 Cookie；运营时限读取失败不创建新会话。ID Token 仍只承担初始短期身份验证。会话到期重新认证，无刷新令牌。HTTP 每个请求在线核验，WebSocket 在握手、每条入站及出站消息前核验，空闲连接每五秒复核（网络超时另最多五秒）；同时检查会话成员。当前所谓流式接口为逐请求轮询，无长时间 HTTP 流。

统一模式所有写方法都需精确 Origin 和 `X-CSRF-Token`，该值由可读 `__Host-rehab_csrf` Cookie 获取，并与服务器会话哈希比对。非同源 Origin 的读请求也拒绝。`POST /api/auth/logout` 销毁本地会话，不宣称源全局退出。`GET /api/auth/config` 提供模式和受控登录 URL；`GET /api/auth/session` 对已核实绑定返回原业务 user，对未绑定用户仅返回身份及 pending_binding，不授业务访问。

管理员须独立核实源永久 subject 和现有 Mongo actor_id。维护命令默认只读：

绑定带有审核版本，身份会话保存登录时的版本。绑定首次建立、角色复核或停用后，先前会话不能获得新授权，须重新认证。历史会话若缺少版本则失效；历史绑定若缺少版本，须由管理员核实相同 issuer、subject、actor 和当前角色后执行下述 `review-role --apply`，然后用户重新登录。先以不带 `--apply` 的命令检查；不要批量猜测绑定或自动补发版本。此为上线兼容要求，本地代码变更没有修改现有数据库。

```bash
DEBUG=false backend/.venv/bin/python backend/scripts/manage_oidc_bindings.py bind \
  --issuer https://identity.example --subject '<已核实永久subject>' \
  --actor-id '<现有Mongo用户ID>' --reviewer '<核实人引用>' \
  --approved-role '<已核实的原角色>' \
  --evidence-reference '<受控核实记录引用>'
```

审阅一致后加 `--apply`。命令写入身份映射、已复核的原角色快照及同文档审计，不创建账号、不复制密码、不变更角色。`disable` 使用相同参数及 `--apply` 停用精确绑定；已有记录不能被 bind 覆盖或复活，同一源下一个业务 actor 不能被多个 subject 占用。若原角色发生变化，该会话失效；管理员用 `review-role` 显式重新核实当前角色，用户重新认证后才生效，旧会话不会复活。核实证据仅存引用，不能在命令参数或数据库里放身份证照片等材料。本轮未提供管理界面，特权维护工具不是普通用户接口。

权限归属按本轮用户决定：身份统一到 113.44，康复权限继续由本系统管理；它不是跨系统集中临床授权。现有患者归属和管理员原有范围仍按原规则执行。上线前须独立核实所绑定旧角色及数据范围，不把任何源研究管理员自动映射为康复管理员。

填报身份委托要求源端私有 `OIDC_CLIENTS_FILE` 中，为该 OIDC 客户端显式配置 `integration_client_id`，其值为同一康复系统所用的源端集成客户端 ID；源端检查一对一关系，不凭两个 ID 相同推断配对。康复侧只从当前统一登录的服务器会话取得源令牌并经 HTTPS 传递；源端解析操作人，拒绝请求自带操作人 ID，令牌不明文保存到填报会话。缺少配对或源端结构迁移时拒绝填报。旧填报会话缺少身份委托材料时不能继续使用；上线迁移须先备份、隔离演练并核对旧任务处置。本地实现不代表已经配置或部署 113.44。

2026-11-14 复核确认上述要求已在源端实现并有测试：缺配对时源端以 503 拒绝填报；源端从 OIDC access token 解析操作人并在请求自带 `operator_user_id` 时拒绝。此外源端在打开、消费与委托请求中核验会话版本与授权代际（`FillSession.authority_generation`，Grant 撤销、成员撤销、客户端降级、中心停用、问卷关闭、受试者退出等入口触发 bump，与业务变更同事务提交；源端有并行在途改动，不锚定行号），提交时核验 presentation token；版本失效或代际落后即拒绝。

隔离测试：`DEBUG=false REHAB_TEST_OIDC_MONGO_URI=mongodb://127.0.0.1:<隔离端口> PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/tests/test_oidc_client.py`。仅接受显式本机 URI，各测试创建并清理独立数据库；测试真实 Mongo 一次性消费、JOSE 与 Cookie 路由，身份提供方 HTTP 使用注入 MockTransport，不修改系统或生产 TLS 策略。两端真实 provider/RP 和真实浏览器联调仍需另外验收（2026-11-14 复核仍未进行；两端均为本地实现，本文不宣称跨端闭环已完成）。
