# T47 本地双端真实 HTTPS 联调演练记录（2026-11-15）

> 目的：为「Rehabman 康复端 ↔ 113.44 康复问卷管理系统（源端）」正式环境联调做一次本地预演：
> 真实 HTTPS 反代（nginx 容器 + 自签证书）+ 两端真实应用进程 + 真实 OIDC 互信 + 端到端填报闭环。
> **本记录即正式部署的操作底稿**：命令序列、配置、坑清单均来自实际跑通的步骤，可照抄。
>
> 结论先行：**全链路演练成功**。创建患者/随访/填报任务 → 源端真实 HTTPS 登录 → launch →
> 嵌入页（HTTPS + 委托会话）→ 草稿 → 恢复 → 正式提交 → 康复端 confirm → 随访审阅 completed，
> 全部通过；`TRUSTED_PROXY_HOPS` 陷阱用 A/B 实验复现并确认修复方式。

## 1. 拓扑

```
浏览器/协议客户端（httpx，trust 演练 CA）
   │  https://127.0.0.1:8443                 │  https://127.0.0.1:8444
   ▼                                          ▼
nginx:1.28.0-alpine 容器（host 网络，自签证书）  （同一个 nginx 的第二个 server 块）
   │ proxy_pass http://127.0.0.1:5000          │ proxy_pass http://127.0.0.1:5502
   │ X-Forwarded-Proto: https, Host: $http_host
   ▼                                          ▼
源端 gunicorn workers=1（deploy/gunicorn.conf.py，production 配置 + SM4 加密 SQLite）
                                              康复端 uvicorn（FastAPI，Mongo 副本集 37022）
```

- 两端应用均为本机真实进程（各自 venv；两端仓库无现成镜像构建路径，按任务约定选本机进程）。
- nginx 与 Mongo 为真实 docker 容器（演练专用，端口 8443/8444/37022，演练完已清理）。
- 源端数据库走**生产同款**路径：明文建库 → `migrate_sm4_database.py` 整库转 SM4 → 生产配置启动。
- 种子数据全部合成（`tests/test_integration_catalog_api._make_base_data(capability_profile='fill')` 等价物）。

## 2. 前置产物（生成命令）

```bash
mkdir -p /tmp/rehearsal-https/{tls,mongo,nginx,source/{instance,auth,audit,tmp,keys,logs},rehab/logs,e2e/logs,scripts}
chmod 700 /tmp/rehearsal-https/source/{auth,audit,tmp,instance}

# 自签 CA + 服务器证书（SAN 必须覆盖实际访问的 IP/域名）
cd /tmp/rehearsal-https/tls
openssl ecparam -name prime256v1 -genkey -noout -out ca.key
openssl req -x509 -new -key ca.key -sha256 -days 30 -subj "/CN=rehearsal-root-ca" -out ca.crt
openssl ecparam -name prime256v1 -genkey -noout -out server.key
openssl req -new -key server.key -subj "/CN=127.0.0.1" -out server.csr
printf 'subjectAltName = IP:127.0.0.1,DNS:localhost,DNS:rehab-source.rehearsal,DNS:rehab-rp.rehearsal\n' > san.cnf
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial -days 30 -sha256 \
  -extfile san.cnf -out server.crt
cat server.crt server.crt > fullchain.pem
cp server.key privkey.pem && chmod 600 privkey.pem   # nginx 容器内按 /etc/rehab-questionnaire/tls/privkey.pem 读取
```

### 2.1 演练 Mongo 副本集（/tmp/rehearsal-https/mongo/compose.yml）

```yaml
name: rehab-https-rehearsal
services:
  mongo:
    image: mongo:7.0.16
    container_name: rehab-https-rehearsal-mongo
    ulimits: { nofile: { soft: 65536, hard: 65536 } }   # 与 deploy/mongodb/compose.yml 一致
    command: ["mongod", "--replSet", "rehearsal_rs", "--bind_ip_all"]
    ports: ["127.0.0.1:37022:27017"]
    healthcheck:
      test: ["CMD", "mongosh", "--quiet", "--eval", "if (!db.hello().isWritablePrimary) quit(1)"]
      interval: 2s
      timeout: 5s
      retries: 60
volumes: { data: {} }
```

初始化（坑 #1）：

```bash
cd /tmp/rehearsal-https/mongo && docker compose up -d && sleep 12
docker exec rehab-https-rehearsal-mongo mongosh --quiet \
  --eval 'rs.initiate({_id:"rehearsal_rs",members:[{_id:0,host:"127.0.0.1:27017"}]})'
# 注意：成员 host 必须写 "127.0.0.1:27017"（容器内视角），与 deploy/mongodb/init-replica.js 相同。
# 写 "127.0.0.1:37022" 会报 No host described ... maps to this node。
```

### 2.2 nginx 反代（/tmp/rehearsal-https/nginx/nginx.conf）

两个 server 块：8443→源端 5000，8444→康复端 5502。与
`康复问卷管理系统/deploy/nginx/conf.d/rehab-production.conf.template` 的差异点（重要）：

```nginx
proxy_set_header Host $http_host;            # 坑 #2：不能用 $host（剥端口，生产 host 校验 400）
proxy_set_header X-Forwarded-Proto $scheme;  # TRUSTED_PROXY_HOPS 的生效前提
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
# 不要照抄模板的 add_header X-Frame-Options SAMEORIGIN always —— 坑 #4
```

```bash
docker run -d --name rehab-https-rehearsal-nginx --network host \
  -v /tmp/rehearsal-https/nginx/nginx.conf:/etc/nginx/nginx.conf:ro \
  -v /tmp/rehearsal-https/tls:/etc/rehab-questionnaire/tls:ro \
  nginx:1.28.0-alpine nginx -g 'daemon off;'
```

### 2.3 源端生产配置（/tmp/rehearsal-https/source/env）

对照 `deploy/production.env.example`，值全部为演练合成密钥：

```bash
FLASK_ENV=production
SECRET_KEY=<64 hex>
SECURITY_AUDIT_KEY=<64 hex，与 SECRET_KEY、SM4 key 三者互不相同>
SM4_DATA_KEY=<32 hex>
DATABASE_SM4_KEY_FILE=/tmp/rehearsal-https/source/keys/database-sm4.key   # 内容 = SM4_DATA_KEY，0600
SM4_SQLITE_DRIVER_PATH=<源端仓库>/.local-only/sm4-sqlite/python
DATABASE_ENCRYPTION=sm4
DATABASE_URL=sqlite:////tmp/rehearsal-https/source/instance/rehab_system.db
SECURITY_AUDIT_DIR=/tmp/rehearsal-https/source/audit
AUTH_STATE_PATH=/tmp/rehearsal-https/source/auth/authentication.sqlite3    # 父目录 0700
PRIVATE_TEMP_DIR=/tmp/rehearsal-https/source/tmp
TRUSTED_PROXY_HOPS=1                       # 本演练的主题：nginx 一层，填 1
PUBLIC_BASE_URL=https://127.0.0.1:8443     # 坑 #3：与实际访问 host 逐字一致（含端口）
OIDC_PROVIDER_ENABLED=1
OIDC_ISSUER=https://127.0.0.1:8443         # 与 PUBLIC_BASE_URL 同源；康复端 FORM_PLATFORM_BASE_URL 必须同源
OIDC_SIGNING_KEY_FILE=/tmp/rehearsal-https/source/keys/signing.pem  # RSA ≥2048，0600
OIDC_CLIENTS_FILE=/tmp/rehearsal-https/source/keys/clients.json
INTEGRATION_RATE_LIMIT_PER_MINUTE=120
MAIL_DELIVERY_MODE=console
```

OIDC 客户端文件（secret_hash 必须是 werkzeug scrypt 格式）：

```python
# 生成命令（源端 venv）
from werkzeug.security import generate_password_hash
clients=[{"client_id":"rehab-interop","name":"Rehabman RP",
  "secret_hash":generate_password_hash("<RP_SECRET>"),
  "redirect_uris":["https://127.0.0.1:8444/api/auth/oidc/callback"],   # 必须显式 https，精确匹配
  "integration_client_id":"test-catalog-client"}]                       # 与 IntegrationClient.client_id 配对（fill.create 依赖）
```

### 2.4 源端建库（生产同款三步）

```bash
cd <源端仓库>
# ① 明文临时库 + 全部表结构/触发器（SECURITY_SCHEMA_MIGRATION 模式，等同 manage_security_schema 工厂初始化）
set -a; . /tmp/rehearsal-https/source/env; set +a; unset DATABASE_ENCRYPTION
touch /tmp/rehearsal-https/source/instance/rehab_plaintext.db   # 0600
venv/bin/python -c "
from app import create_app
app = create_app('production', config_overrides={
    'SQLALCHEMY_DATABASE_URI': 'sqlite:////tmp/rehearsal-https/source/instance/rehab_plaintext.db',
    'SECURITY_SCHEMA_MIGRATION': True}, initialize_database=True)"
# 注意：必须 unset DATABASE_ENCRYPTION 但保留 SM4_DATA_KEY —— production 下 configure_security
# 无条件校验 SM4_DATA_KEY（与加密开关无关）。

# ② 整库转 SM4（82 表，校验通过；--target 父目录必须 0700）
venv/bin/python scripts/migrate_sm4_database.py \
  --database /tmp/rehearsal-https/source/instance/rehab_plaintext.db \
  --target   /tmp/rehearsal-https/source/instance/rehab_system.db \
  --key-file /tmp/rehearsal-https/source/keys/database-sm4.key \
  --driver-path <源端仓库>/.local-only/sm4-sqlite/python \
  --apply --maintenance-confirmed

# ③ 种子（create_app('production') + fixture 等价物；SM4 库上直接跑）
set -a; . /tmp/rehearsal-https/source/env; set +a
venv/bin/python /tmp/rehearsal-https/scripts/seed_source_fill.py
# 种子内容：Organization/Project/ProjectCenter/Questionnaire(+版本族)/Question/
# IntegrationClient(fill, scopes)/ProjectMembership/User(interop_doctor, interop_admin)/
# Patient/Subject/PatientArchive（见坑 #8）
```

### 2.5 康复端配置（/tmp/rehearsal-https/rehab/env）

```bash
MONGODB_URL='mongodb://127.0.0.1:37022/?replicaSet=rehearsal_rs&directConnection=true'  # 坑 #5：值含 & 必须加引号
DATABASE_NAME=rehab_https_rehearsal
ENVIRONMENT=development
SECRET_KEY=<hex>
FORM_PLATFORM_BASE_URL=https://127.0.0.1:8443    # 必须与源端 OIDC_ISSUER 同源（SOURCE_ORIGIN 校验）
FORM_PLATFORM_CLIENT_ID=test-catalog-client
FORM_PLATFORM_CLIENT_SECRET=catalog-client-secret
FORM_PLATFORM_VERIFY_TLS=true                    # 自签证书可用：见坑 #6（certifi 信任包）
FORM_PLATFORM_FILL_ENABLED=true                  # 直接读 os.environ，不走 pydantic settings
OIDC_ENABLED=true
OIDC_AUTHENTICATION_MODE=oidc                    # 统一登录：本地密码登录被 403 封禁
OIDC_ISSUER=https://127.0.0.1:8443
OIDC_PUBLIC_BASE_URL=https://127.0.0.1:8444      # 必须 https（__Host- cookie 前缀要求）
OIDC_CLIENT_ID=rehab-interop
OIDC_CLIENT_SECRET=<RP_SECRET>
OIDC_SESSION_ENCRYPTION_KEY=<Fernet key>
```

**自签证书信任（坑 #6）**：康复端 `OidcClient` 与 `FormPlatformClient` 的 httpx 客户端
`verify` 均为 bool，不接受 CA 路径；httpx `verify=True` 走 certifi 打包的 CA 集。
本演练的做法（生产等价：把正式 CA 装进镜像/venv 的 certifi 信任包）：

```bash
CERT=$(ls backend/.venv/lib/python*/site-packages/certifi/cacert.pem)
cp "$CERT" /tmp/rehearsal-https/rehab/cacert.pem.orig   # 备份
cat /tmp/rehearsal-https/tls/ca.crt >> "$CERT"          # 追加演练 CA
```

启动：

```bash
# 源端
cd <源端仓库> && set -a && . /tmp/rehearsal-https/source/env && set +a
nohup venv/bin/gunicorn --config deploy/gunicorn.conf.py 'deploy.wsgi:app' &   # workers=1 必须（限流/写锁进程内存）

# 康复端
cd backend && set -a && . /tmp/rehearsal-https/rehab/env && set +a
nohup .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 5502 &
```

## 3. 端到端链路（每步实测结果）

驱动脚本（协议级浏览器语义，httpx + cookie jar + 手动重定向；演练 CA 校验开启）：
`/tmp/rehearsal-https/e2e/driver.py`，阶段：login → bindings → admin → doctor → fill → confirm。

| # | 步骤 | 实测结果 |
|---|------|---------|
| 1 | RP `GET /api/auth/oidc/start` | 303 → IdP authorize（PKCE S256 + nonce） |
| 2 | IdP `GET /oidc/authorize`（未登录） | 302 → `/auth/login?next=…` |
| 3 | 登录页 + `GET /auth/captcha`（PNG） | 200；验证码明文不落盘，演练持密钥离线还原后真实提交（见坑 #7） |
| 4 | IdP `POST /auth/login`（csrf+captcha） | 302 → authorize |
| 5 | IdP consent `POST decision=allow` | 302 → RP callback（code+state） |
| 6 | RP `GET /api/auth/oidc/callback` | 303（token 交换/jwks/introspect 全部走 HTTPS 200） |
| 7 | RP `GET /api/auth/session` | 200 `identity_state=pending_binding`（绑定前） |
| 8 | `manage_binding`（issuer+subject→本地 actor，admin/doctor 双绑定） | 绑定后 session `clinical_access=true` |
| 9 | `POST /api/admin/patients`（admin） | 201，患者创建 |
| 10 | `GET /api/integrations/forms/catalog/projects`（admin） | 200，远端目录经 FormPlatformClient HTTPS 拉取 |
| 11 | `POST /api/integrations/forms/patient-links` | 201，远端 patient-reference 校验通过（status=verified） |
| 12 | `POST /api/integrations/forms/form-bindings` | 201，远端 current version 校验通过 |
| 13 | `POST /api/users/patients/{id}/practitioners`（doctor 本人） | **403**，admin 会话补做 200（坑 #9） |
| 14 | `POST /api/doctors/follow-ups`（doctor） | 201，随访 status=scheduled |
| 15 | `POST /api/integrations/forms/fill-tasks`（带 followup_visit_id） | 200；源端 create 走 HTTPS + `X-Source-Access-Token` 委托 → secure 校验通过 |
| 16 | `POST /api/integrations/forms/fill-tasks/{id}/launch` | 200 `mode=launch`，`Cache-Control: no-store`，action=https://127.0.0.1:8443/integration/embed/&lt;uuid&gt; |
| 17 | 浏览器 `POST /integration/embed/<uuid>`（Origin=RP 精确匹配） | 303 → 填报页；**Set-Cookie `SameSite=None; Secure` 确认** |
| 18 | token 重放 | 410（一次性消费确认） |
| 19 | `GET` 嵌入填报页 | 200；CSP 放开为 `frame-ancestors 'self' https://127.0.0.1:8444`；presentation token 存在 |
| 20 | `POST …/submit`（submit_type=draft） | 302，草稿落库 |
| 21 | RP 再次 launch | 200 `mode=resume`（无 token） |
| 22 | `GET /integration/resume/<uuid>`（同一浏览器会话） | 303 → 带 response_id 的填报页；草稿内容恢复确认 |
| 23 | 无会话浏览器 resume | **403**（委托会话守卫确认） |
| 24 | `POST …/submit`（submit_type=submit，带 response_id） | 302 → submission_success |
| 25 | RP `POST …/fill-tasks/{id}/confirm` | 200，任务 confirmed；远端核实 response_id=4、answers 落证据 |
| 26 | 随访联动 | confirm 后 followup `status=in_review`（effective_response 外部答卷证据） |
| 27 | `POST /api/health-records/followups/{id}/review`（approved） | 200，followup `status=completed`，闭环完成 |

响应头断言：两端 HSTS `max-age=31536000`、`X-Content-Type-Options: nosniff` 全部在位；
TLS 链：客户端仅信任演练 CA（`verify=ca.crt` 上下文），康复端服务端→源端调用同样真实验证。

## 4. TRUSTED_PROXY_HOPS A/B 实验（探查报告陷阱复现）

仅改 `TRUSTED_PROXY_HOPS=0` 重启源端（其余不变）：

| 请求 | hops=1 | hops=0 |
|------|--------|--------|
| `GET /.well-known/openid-configuration` | 200 | **308**（production 强制 HTTPS 重定向） |
| `POST /integration/v1/fill-sessions`（合法 Bearer） | 过 secure 校验 → 403 invalid_source_identity（缺委托 token，符合预期） | **400 「请通过HTTPS提交请求」** |
| `POST /integration/v1/fill-sessions/<uuid>/launch` | 同上 | **400 「请通过HTTPS提交请求」** |

恢复 hops=1 后 discovery 200、create 进入身份校验层。结论：nginx 必须发
`X-Forwarded-Proto $scheme` 且应用 `TRUSTED_PROXY_HOPS=1`（ProxyFix `x_proto=hops`，
`application_security.py`），否则 OIDC 全部 400、create/launch 全部 400、嵌入 cookie 无 Secure。
注：production 模式下 host/HTTPS 强制层（before_request）先于 integration 的
`secure_transport_required` 检查触发，报错文案不同但根因相同。

## 5. 坑清单（正式部署逐条核对）

1. **Mongo 副本集初始化的成员 host**：容器内 `rs.initiate` 必须写 `127.0.0.1:27017`（与
   `deploy/mongodb/init-replica.js` 一致）；写宿主侧映射端口报 `No host described in new configuration`。
   康复端填报事务强制副本集（standalone → 503 FOLLOWUP_TRANSACTION_UNAVAILABLE）。
2. **nginx `proxy_set_header Host $host` 会剥端口**：production 的 host 信任校验
   （`request.host` vs `PUBLIC_BASE_URL` netloc）对含端口地址直接 400「请求站点不受信任」。
   端口显式暴露的部署必须用 `$http_host`；生产用默认 443 + 无端口域名时二者等价。
3. **PUBLIC_BASE_URL / OIDC_ISSUER / 康复端 FORM_PLATFORM_BASE_URL 三者必须同源**且与实际
   访问 host 逐字一致（含端口）；康复端 `delegation.issuer == client.source_origin` 校验
   不一致 → fill-tasks 403。
4. **nginx 模板自带的 `add_header X-Frame-Options SAMEORIGIN always` 会压过应用按嵌入会话
   放开的 frame-ancestors**：嵌入联调的 nginx 配置必须去掉该行（应用层已按
   `integration_fill_session.origin` 放开 CSP）。本演练实测嵌入页 CSP=
   `frame-ancestors 'self' https://127.0.0.1:8444`。
5. **env 文件值含 `&` 必须加引号**：`MONGODB_URL=…&directConnection=true` 未加引号时 `&`
   被 shell 当后台分隔符，变量实际未导出，应用静默回落默认 `localhost:27017`（30s 超时后
   启动失败）。systemd EnvironmentFile 也按此规则检查。
6. **自签证书信任**：康复端 OIDC 客户端与 FormPlatformClient 的 httpx `verify` 仅接受 bool，
   不能传 CA 路径；`verify=True` 走 certifi 信任包。正式部署需把 CA 追加进运行环境的
   certifi `cacert.pem`（或部署内部 CA 进镜像），不能靠系统信任库（httpx 不读）。
   本演练即用该方式实现 `FORM_PLATFORM_VERIFY_TLS=true` 的真实验证。
7. **源端登录验证码不可绕过**：明文不落盘（仅 HMAC-SHA256 摘要，无 testing 短路、一次性
   消费、5 分钟过期）。真人浏览器读图即可；协议级驱动必须离线还原（本演练持部署密钥读
   AUTH_STATE 库摘要 + 本地 4 位穷举）。另注意限流：LOGIN_ACCOUNT_ATTEMPTS=5/15min，
   重跑演练需等窗口过期或按运维方式清理 AUTH_STATE 库 `rate_limit` 行。
8. **种子缺 PatientArchive 会 409**：patient-links 的远端 patient-reference 要求
   `PatientArchive(patient_id, organization_id, status='active')` 行，fixture 基础数据不含，
   需补种（正式部署是真实数据天然存在）。
9. **主治关联权限**：`POST /api/users/patients/{id}/practitioners` 医生本人 403，需 admin
   会话执行（PATIENT_UPDATE 权限归属）；生产流程应把该步放入管理员工作台。
10. **委托填报的浏览器会话约束**：resume 要求与 token 消费**同一个源端会话**（cookie 内
    `integration_fill_session`）；正式提交必须带恢复页返回的 `response_id`（否则 409
    「请从原填报任务恢复当前草稿」）。嵌入 iframe 内这两点天然满足，纯脚本驱动需注意。
11. **certifi 补丁需随镜像维护**：venv 升级会重置信任包；建议在镜像构建步骤固化 CA 注入。
12. **AUTH_STATE 库与主库同一加密体系**（SM4）：运维排查需用 SM4 驱动连接，不能用裸 sqlite3。

## 6. 演练清理（已完成）

```bash
kill <gunicorn pid> <uvicorn pid>
docker rm -f rehab-https-rehearsal-nginx
cd /tmp/rehearsal-https/mongo && docker compose down -v
cp /tmp/rehearsal-https/rehab/cacert.pem.orig <venv certifi cacert.pem>   # 还原信任包
rm -rf /tmp/rehearsal-https
```

演练未 commit 任何代码；未触碰 37021 共享副本集；Rehabman/源端生产代码零改动
（演练辅助脚本均放 /tmp，本文件为唯一入库产物）。
