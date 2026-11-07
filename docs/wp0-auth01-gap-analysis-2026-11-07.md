# WP0 / AUTH01 两端缺口分析（设计前置文档）

- 日期：2026-11-07（Asia/Singapore）
- 性质：只读代码核查产出，未修改任何现有代码，未执行 git 操作。
- 范围：Rehabman（medicalassistant，FastAPI + MongoDB）与 113.44（康复问卷管理系统，Flask + flask_login + SQLAlchemy）两个本地仓库的当前工作区状态。
- 关联文档：[统一身份契约草案](./identity-integration-contract.md)、[首轮嵌入填报试点](./first-integration-pilot.md)、[开发计划](./development-plan-2026-11-07.md) AUTH01。
- 证据约定：所有结论附 `file:line`；无法从代码直接确认的标注「待核实」。本文不记录任何真实密码、密钥或 token；113.44 仓库路径下文简写为「问卷系统」。

## ① Rehabman 认证现状与缺口

### 1.1 JWT 签发与校验

| 环节 | 位置 | 现状 |
|---|---|---|
| Bearer 提取 | `backend/app/core/auth.py:21` | `OAuth2PasswordBearer(tokenUrl="/api/users/login")` |
| 访问令牌解码 | `backend/app/core/auth.py:24-40` | `jose.jwt.decode`，强制 `require_exp`，校验 `sub` 与 `token_type=access`；旧版无 `token_type` 的令牌兼容放行 |
| 签发 | `backend/app/services/user_service.py:420-460` | HS 对称算法（`settings.ALGORITHM`/`settings.SECRET_KEY`），访问令牌 + 可选刷新令牌（:437-460） |
| 刷新 | `backend/app/services/user_service.py:482-486`、`backend/app/api/routers/user_router.py:113-139` | 刷新令牌为 JWT，`/refresh-token` 接受请求体中的 refresh_token |
| 当前用户依赖 | `backend/app/core/auth.py:43-70` | 解码后经 UserService 查 Mongo，校验 `is_active`（:68-69） |
| 激活用户依赖 | `backend/app/core/auth.py:72-81` | 对 `get_current_user` 结果重复校验 `is_active` |
| WebSocket 鉴权 | `backend/app/core/auth.py:84-116` | 依次尝试 query 参数 `token`（:93）与 Cookie；query 传 token 与契约 §5「不在 URL 放长期令牌」冲突，属遗留面 |
| 依赖别名 | `backend/app/core/dependencies.py:23-28` | `dependencies.get_current_user` 只是 `auth.get_current_user` 的 re-export，两套导入实为同一函数，收敛时只需统一导入源 |

密码哈希：`backend/app/services/user_service.py:585-597`，bcrypt 哈希与校验；`authenticate_user`（:382-393）对所有账号（含演示账号）强制哈希比对，注释明确「不得仅凭邮箱放行」。

### 1.2 各 router 鉴权依赖盘点（逐个核查）

挂载见 `backend/app/main.py:193-231`。结论：**除 user_router 的登录/注册与两个 router 外，其余全部路由已带 `get_current_user`/`get_current_active_user` 依赖**。

| Router | 鉴权依赖 | 缺口 |
|---|---|---|
| `rehabilitation_router.py`（挂载 `/api/rehabilitation`，main.py:194） | **完全没有**：全部端点只依赖 `get_rehabilitation_service`，`backend/app/api/routers/rehabilitation_router.py:22-439` | 最大缺口。含大量写操作：计划创建/更新/删除（:66-106）、LLM 生成与批准（:22-63）、阶段变更（:304）、进度记录（:325）、调整应用（:359）；读接口可按 `patient_id` 枚举（:107-115、:249-267），无任何来源主体与资源归属校验 |
| `agent_router.py`（挂载 `/api/agents`，main.py:195） | **完全没有**：`backend/app/api/routers/agent_router.py:10-93` | 代理增删改查与 LLM 参数生成（:84-93）均无鉴权 |
| `user_router.py` | `/me`、管理端点有依赖（:141-293）；登录/注册/刷新按设计匿名（:23-139） | 问题不在缺依赖，而在**平行人员管理能力**（见 1.3） |
| `analytics_router.py` | `:15,44,73,103` 四端点均带 `get_current_active_user` | 无 |
| `audit_log_router.py` | `:54,123,160` | 无（但审计写入侧身份提取有缺口，见 1.5） |
| `communication_router.py` | `:35-198` 十端点 | 无 |
| `data_filter_router.py` | `:107-310` 七端点（经 dependencies 别名） | 无 |
| `device_analysis_router.py` | `:107-294` | 无 |
| `device_data_standard_router.py` | `:19,86,108` | 无 |
| `device_repair_router.py` | `:23,73,109` | 无 |
| `device_router.py` | `:91-227` | 无 |
| `doctor_router.py` | `:17-273` | 无 |
| `health_alert_router.py` | `:27-362` | 无 |
| `health_manager_router.py` | `:12-95` | 无 |
| `health_record_router.py` | `:36-639` 二十二端点 | 无 |
| `notification_router.py` | `:22-87` | 无 |
| `patient_router.py` | `:20-310` | 无 |
| `report_scheduler_router.py` | `:94-259` | 无 |
| `system_admin_router.py` | `:22-237` | 无 |
| 集成填报（试点新增） | `backend/app/integrations/forms/router.py:41,55,80,100,115` 全部 `get_current_active_user` | 无 |

权限依赖（`require_permission`，`backend/app/core/permissions.py`）目前**只在 user_router 的管理端点使用**（user_router.py:162,177,187,198,219,233,258,273,287）。其余 router 即使有登录依赖，路由内对「来源主体 vs 资源归属」的校验深度参差，多数交给 service 层判断——逐 service 的资源级校验覆盖率为 AUTH01 后续需补的清单（待核实，本档只确认依赖层现状）。

### 1.3 平行人员管理与本地注册旁路（AUTH01「没有平行人员管理」项）

- 本地患者自注册：`backend/app/api/routers/user_router.py:23-30` `POST /api/users/register`，接受 email/name/password 创建本地账号（schema `backend/app/schemas/user.py:37-47`）；前端仍在调用（`frontend/src/store/slices/authSlice.ts:56-65` 指向 `${API_BASE_URL}/users/register`）。
- 本地密码登录/刷新：user_router.py:32-78（`/login`）、:80-111（`/login/refresh`）、:113-139（`/refresh-token`）。
- 平行人员管理端点（管理员在本地直接建号/改角色/改状态）：
  - `POST /create` 建任意角色账号（user_router.py:182-190）；
  - `PUT /{user_id}` 可改 `password`、`role`、`is_active`（user_router.py:192-212；`UserUpdate` schema 含这三个字段，schemas/user.py:57-63）；
  - `DELETE /{user_id}` 实为停用（user_router.py:214-226）、`POST /activate/{user_id}`（:253-265）、`POST /permissions`（:228-251）；
  - 患者—医护指派 `POST/DELETE /patients/{id}/practitioners`（:267-293）。
- 这些端点在统一身份切换时须按契约 §10.4 同批关闭或收编为仅同步投影的管理工具，只改前端按钮不算完成。

### 1.4 通用自助资料接口现状（AUTH01「不可修改密码、账号状态及授权」项）

- `PUT /api/users/me`（user_router.py:148-155）使用 `SelfUserUpdate`（schemas/user.py:50-54，`extra="forbid"`，仅 `name` 字段），服务端注释明确「账户与凭据不通过此接口修改」。**现状已满足要求**，但该约束仅由 schema 单点保证，建议以负向测试固化（改密码/角色/is_active 的请求必须 4xx）。
- `GET /me`（:141-146）仅读，无问题。
- 全仓未发现其他「自助改密」端点（grep routers 无 password 修改路由）。

### 1.5 演示账号与审计身份提取（已知断点复核）

- 「空数据库启动创建默认演示账号」**已修复**：启动钩子只连接数据库与初始化 WebSocket（`backend/app/main.py:109-122`），无任何 seed 调用；演示账号初始化改为显式工具 `backend/app/tools/seed_demo.py:13-54`，带 `medicalassistant_demo_` 前缀库名校验与 `demo_seed_manifest` 幂等标记，仅测试引用（`backend/tests/test_demo_auth_boundary.py`）。说明见 `docs/isolated-demo-accounts.md`。
- 「绕过密码哈希的演示账号认证」后端**已无此路径**：`authenticate_user` 对含演示账号在内的一切账号强制 bcrypt 比对（user_service.py:391-393）。残留面在前端：`frontend/src/store/slices/authSlice.ts:213-227` 仍硬编码四组演示邮箱与预设密码的 `mock*Login` thunk（走真实登录接口）。它不绕过后端哈希，但把公开演示凭据带进了前端构建，AUTH01 验收应要求从生产构建移除（是否保留开发模式入口待与 D04 一并确认——待核实）。
- 审计身份提取**不完整（确认）**：`backend/app/core/permission_audit.py:87-95` 中 `user_id = None`，token 解码逻辑整段被注释（:94 `# user_id = decode_token(token)["sub"]`），审计记录落到 `user_id="anonymous"`（:149）；写审计的 `:176-242` 入参也依赖调用方传入。AUTH01 范围内应先用现成的 `_access_token_user_id`（auth.py:24）或依赖注入补全。

### 1.6 小结：Rehabman 侧 AUTH01 待办

1. rehabilitation_router、agent_router 补统一鉴权依赖与资源归属校验（唯一「完全没有鉴权」的两处）。
2. permission_audit 身份提取补全。
3. 平行人员管理端点（1.3 列表）制定关闭/收编方案，与统一登录切换同批发布。
4. PUT /me 的边界负向测试固化。
5. 前端演示快捷入口的生产构建处置。
6. WebSocket query-token 的收敛（契约 §5，可与 AUTH03 一并处理）。

## ② 113.44 权威数据源盘点

### 2.1 账号与凭据（User）

`app/models/user.py:13-100`：

- 全局角色四档：`superadmin/admin/org_manager/user`（:83），另有 `account_type`（个人/机构账号）与 `organization_id`（:78-80 附近）；**无临床角色**——契约 §3.1 要求临床身份独立建模，现有 role 不能直接充当医生身份（契约 §2 已声明）。
- 凭据与状态：`password_hash`、`password_changed_at`、`password_history_json`、`must_change_password`、`is_active`、`auth_session_token`（登录会话单 token 字段，具备作废单点）。
- MFA：`totp_secret_ciphertext`、`totp_enabled_at`、`totp_last_counter`、`totp_recovery_hashes`——AUTH01 复用其认证控制时不得绕过。
- 第三方标识：微信 `wechat_openid/unionid`（:53-57）与 `ExternalIdentity` 关系（:59-66，注明旧字段已废弃、新记录归 ExternalIdentity）。

### 2.2 机构、项目、中心、成员

| 模型 | 位置 | 可作权威源的字段 |
|---|---|---|
| Organization | `app/models/organization.py`（被 ProjectCenter 引用，`app/models/project.py:141`） | 机构主数据 |
| ProjectCenter | `app/models/project.py:130-149` | `project_id + organization_id + center_code` 唯一，`is_primary`、`status` —— 中心归属权威 |
| ProjectMembership | `app/models/project.py:193-260` | `role_code`（project_manager/cra/crc/test_user，:203-206）、`center_id`、`questionnaire_id`（表单范围）、`status`（active/revoked）、`assigned_by_id/assigned_at`、`revoked_at`、`valid_until`、`fill_quota/fill_count` —— 与契约 §6 要求的授权范围对象（project/center/form/valid_until）高度对应，缺 `purpose`、`grant_id/version` |
| Subject | `app/models/project.py:412-455` | `project_id + patient_id + subject_code` 唯一，`center_id`，状态机 screening/enrolled/withdrawn/completed —— 项目受试者权威 |
| Patient | `app/models/patient.py` | 区分全局身份与机构档案（契约 §2 引 patient.py:7）；账号≠Patient，本人/代办关系模型尚不存在（契约 §3.2 `AccountPatientLink` 待建） |

成员管理写入路径：`app/routes/project.py:837` 附近（契约 §2 引用；本轮未逐行复核，待核实）。项目填报依赖 `current_user` 与 `app/services/project_permission_service.py`（契约 §2 已指出 :231,756,773 的「未分中心」宽容语义，新集成协议须默认拒绝）。

### 2.3 登录、注册与邮箱验证流程

- 登录 `app/routes/auth.py:164-206`：验证码（:176-184）、15 分钟限流（:168-169）、账号 `is_active` 检查（:184-188）、MFA 分支（:189-191 经 `_stage_mfa_login`）。AUTH01 复用该流程作为权威认证，不旁路 MFA/停用状态。
- 注册 `app/routes/auth.py:329-406`：邮箱验证码；**按输入机构名 `ilike` 匹配或直接新建机构并写入 `organization_id`（:355-373）**——契约 §4.1 明确康复注册路径不得沿用「机构名即成员资格」，此行为是 AUTH05 需求的改造点，AUTH01 文档仅登记。
- 邮箱验证：`RegistrationEmailVerification` 模型（`app/models/user.py:451`）+ `POST /register/email-code`（auth.py:453）。
- 改密/重置：`/change-password`（auth.py:531）、`/forgot-password`（:562）、`/reset-password/<token>`（:608）、`PasswordResetToken`（user.py:409）。这些是权威自身接口，Rehabman 侧不应出现平行实现。

### 2.4 试点沉淀的集成模型（已存在，可作 AUTH01 基础）

- `IntegrationClient`（`app/models/integration.py:43-119`）：`client_id`、`secret_hash`（SHA-256 + `secrets.compare_digest`）、`scopes_json`（project/center/questionnaire 三维白名单）、`status`、`expires_at`；`allows()`（:100-111）注释明确「任一项缺失即拒绝，不沿用空=不限的旧语义」。
- `FillSession`（integration.py:126-180）：`session_uuid`、`embed_token_hash`、`client_id`、`operator_user_id`、project/center/subject/questionnaire/version/visit 全绑定、`ma_task_ref`（发起方任务引用，仅追溯不做授权依据）、`allowed_origin`、状态机 created/embedded/submitted/cancelled/expired、`expires_at`。
- `ExternalIdentity`（`app/models/external_identity.py:11-37`）：`provider/provider_app_id/subject_id/union_id`。**注意**：它当前承载的是 113.44 作为客户端的微信登录记录，语义上不是「113.44 作为身份提供方」的主体映射表，但字段结构（provider+subject_id）与契约 §3.1 `issuer+subject` 同构，可作为拟建 `IdentityClient/Grant` 的参考而非直接复用（待核实是否有非微信 provider 数据）。
- 集成路由 `app/routes/integration.py`：`/v1/fill-sessions` 创建（:118）、查询（:207）、取消（:219）、答卷结果查询（:235）、`/embed/<token>` 一次性令牌换委托会话（:268）、委托会话 Cookie 放宽（:358）、委托会话守卫（:411）。**没有** identity/principal、authorization/check、identity/changes 端点。

## ③ 契约草案 vs 现状差距清单

### 3.1 契约要求、两端均未实现

| 契约条款 | 要求 | 现状 |
|---|---|---|
| §5/§8 OIDC 或标准身份提供 | 发现文档、授权端点、令牌端点、客户端注册与密钥轮换 | 两端均无；契约 §2 自身已声明。D11 协议选型未冻结 |
| §8 `GET /integration/v1/identity/principal` | 最小源身份、状态、版本 | 问卷系统无此端点（integration.py 全表见 2.4） |
| §8 `POST /integration/v1/authorization/check` | 指定 actor/action/resource/purpose 的在线判定 | 无 |
| §8 `GET /integration/v1/identity/changes?cursor=` | 账号/成员/授权失效控制流（AUTH04） | 无；ProjectMembership 有 `status/revoked_at/valid_until` 字段可作事件源，但无变更事件写入与游标投递 |
| §3.2 `ClinicalIdentityApplication` / `ClinicalMembershipInvitation` / `AccountPatientLink` / `ClinicalCapabilityGrant` | 医护申请/邀请审核、账号—患者核实、临床授权 | 问卷系统 models/ 下无对应表；现有 ProjectMembership 角色均为研究角色（project.py:203-206） |
| §3.2 medicalassistant 侧投影 `ExternalPrincipal` / `AuthorizationProjection` / `ExternalPatientLink` / `ApplicationSession` | 本地最小投影与新鲜度 | Rehabman Mongo models/ 无对应集合（models 目录清单见本文开头核查）；试点仅用 `IntegrationFillTask` 隔离模型（first-integration-pilot.md:46） |
| §6/§9 身份与授权版本号（`identity_version`/`authorization_version`、不可倒退） | 撤权失效与对账基础 | 两端均无版本字段；User/ProjectMembership/FillSession 均不含 version |
| §7 `fill_mode` 区分 `self_fill` / `practitioner_on_behalf` | 代填关系显式化 | FillSession 无 fill_mode 字段（integration.py:129-180）；答卷记录 operator，但模式区分未见（待核实 Response 侧是否记录） |
| §5 URL 令牌 | 不在 URL 放长期令牌 | Rehabman WebSocket 支持 query token（auth.py:93） |

### 3.2 已实现或部分实现（可作设计基线）

| 契约条款 | 现状证据 |
|---|---|
| §7 嵌入会话生命周期 `issued → consumed/active → submitted/expired/revoked` | FillSession 状态机（integration.py:130-135,171-180）；试点验证一次性令牌重放被拒（first-integration-pilot.md:29） |
| §7/§8 客户端凭证 + 操作人委托双重校验 | `_require_client`（routes/integration.py:53）+ `operator_user_id` 绑定；客户端 secret 仅哈希存储（integration.py:113-117） |
| §6 默认拒绝 | `IntegrationClient.allows()` 任一范围缺失即拒（integration.py:100-111）；试点实测空中心/无成员/撤权受试者全部被拒（first-integration-pilot.md:30） |
| §7 frame 与 Cookie 边界 | `frame-ancestors` 按会话 allowed_origin 输出、SameSite=None 仅委托会话内、管理端点白名单拒绝（routes/integration.py:358、:411；试点记录 :27-28） |
| §7 后端远端核验为准 | confirm 一致性校验 RESPONSE_MISMATCH（试点 :31；Rehabman router.py:97-110） |
| §1 表单定义/答卷/评分归 113.44，Rehabman 管业务 | 集成填报模块分层与契约一致（backend/app/integrations/forms/） |

### 3.3 契约与现状一致、无需新建的部分

- 契约 §1.1「113.44 为账号权威」：Rehabman 本地注册/登录/人员管理端点（1.3 清单）即需关闭的「平行体系」本体，改造 = 收敛而非新建。
- 契约 §11「旧本地注册/登录/刷新直接调用不能绕过」：验收对象即 1.3 列出的端点。

## ④ 试点已验证可复用机制

以下机制已在隔离联调中端到端验证（证据统一见 first-integration-pilot.md:20-47），AUTH01/AUTH03 设计可直接沿用其协议形态：

1. **委托会话机制**：`FillSession` 全资源绑定 + 一次性 embed token（哈希存储、用后作废、重放 409）+ 委托会话 Cookie 仅会话内改写 `SameSite=None; Secure` + `frame-ancestors` 按 `allowed_origin` 输出。复用注意：一次性令牌使刷新/重开需重建任务，正式接入前需按任务为单位重建会话（试点 :45 已登记此局限）。
2. **Bearer 客户端凭证**：`IntegrationClient`（client_id + 哈希 secret + 三维 scope 白名单 + status/expires_at），Rehabman 侧 `FormPlatformClient`（backend/app/integrations/forms/client.py）以服务端对服务端方式调用，`FORM_PLATFORM_VERIFY_TLS` 默认开启校验。复用注意：客户端 scope 不代替 actor 权利（契约 §8），fill-session 创建仍须带操作人委托上下文。
3. **确认一致性核验**：提交后以后端远端查询为准，浏览器 postMessage 仅作刷新提示；引用不匹配拒绝（RESPONSE_MISMATCH）。
4. **Rehabman 侧填报任务路由鉴权模式**：`get_current_active_user` + 患者归属校验（`PATIENT_NOT_ASSIGNED` 403），可作为其余 Rehabman 路由收敛的参照实现（backend/app/integrations/forms/router.py:38-117）。
5. **隔离演示环境边界**：seed_demo 显式工具 + `medicalassistant_demo_` 库名约束 + demo_seed_manifest（docs/isolated-demo-accounts.md），可作为契约 §10.5「演示环境明确隔离」的既有基础。

## ⑤ AUTH01 实施顺序建议

### 阶段一：Rehabman 侧收敛（不依赖业务决策，可立即开工）

1. **康复路由统一鉴权依赖收敛**（最高优先，AUTH01 完成标准「所有新增及改造接口校验来源主体与资源」的直接缺口）：
   - rehabilitation_router、agent_router 全部端点补 `get_current_active_user`；
   - 写操作与按 `patient_id`/`plan_id` 读取的端点补资源归属校验（参照 forms/router.py 的患者归属模式）；
   - 注意 `main.py:194-195` 的挂载顺序与既有路由声明顺序注释（rehabilitation_router.py:178-179 的路径匹配顺序说明）不受影响。
2. **审计身份提取补全**：permission_audit.py:87-95 改用 `_access_token_user_id` 或请求依赖注入；审计关联真实 actor（契约 §9 要求「不得仅记录系统账号操作」）。
3. **自助资料边界固化**：PUT /me 负向测试（改 password/role/is_active 必须 4xx）；同时确认 `UserUpdate`（schemas/user.py:57-63）中 password/role/is_active 字段随 1.3 收编方案一并处置。
4. **演示账号边界复查**：后端已达标（1.5）；前端 mock*Login 从生产构建移除（开发模式去留可与 D04 会话体验一并定，但不阻塞 AUTH01）。
5. **重启/多 worker 验证**：JWT 为无状态校验，理论多 worker 安全；需验证 startup 无 seed、无内存态会话依赖，并留验收记录。

### 阶段二：契约落地的设计前置（依赖决策，先设计后实现）

| 依赖决策 | 影响 | 建议时序 |
|---|---|---|
| **D11** 协议与库 | 决定 §8 身份提供接口是走 OIDC 标准端点还是契约自定义 `/integration/v1/identity/principal` + `authorization/check`；同时决定缓存最大年龄与不可用策略（契约 §12） | 最先冻结，AUTH03 之前 |
| **D02** 核实与审批责任 | 决定 `ClinicalIdentityApplication`、`ClinicalMembershipInvitation`、`AccountPatientLink` 的字段与流程归属；决定旧本地 actor_id → `issuer+subject` 的人工核实映射方案（契约 §10.2） | 与 D11 并行评审；实现排在协议冻结后 |
| **D04** 域名与嵌入部署 | 影响回调地址、Cookie 边界与前端 demo 入口处置；正式接入须先可信 HTTPS（试点 :49-51 前置条件） | AUTH03 前 |
| 撤权失效（identity/changes、授权版本） | 属 AUTH04 范围；AUTH01 只需在设计上预留 `authorization_version` 字段位与 FillSession 扩展（fill_mode 等） | AUTH04 |
| 113.44 注册流程改造（机构名即关联，auth.py:355-373） | 属 AUTH05 统一注册入口；AUTH01 文档仅登记为兼容方案输入 | AUTH05 |

### 建议的 AUTH01 验收对照（按开发计划 :120 完成标准逐项）

| 完成标准 | 现状 | 缺口动作 |
|---|---|---|
| 所有新增及改造接口校验来源主体与资源 | 除 rehabilitation/agent 外均有登录依赖 | 阶段一第 1 项 |
| 没有平行人员管理 | 平行端点仍在（1.3） | 收编/关闭方案与统一登录切换同批发布 |
| 禁用绕过密码哈希的演示账号认证 | 后端已强制哈希（user_service.py:391-393）；seed 已显式化 | 前端演示凭据出生产构建 |
| 通用自助资料接口不可修改密码、账号状态及授权 | PUT /me 仅 name（schemas/user.py:50-54） | 负向测试固化 |
| 重启/多 worker 验证 | 未执行（待核实是否有既有验证记录） | 阶段一第 5 项 |
