# WP1 API01/API02 设计草案：113.44 对外契约、错误码、分页与 IntegrationClient/Grant 正式化

状态：设计草案（未实现）。对应开发计划 `docs/development-plan-2026-11-07.md:132-141` 的 API01（版本化 OpenAPI 契约、错误码、分页和权限语义）与 API02（独立 IntegrationClient/Grant、范围校验、到期/吊销/轮换/限流）。
依据：113.44 试点实现 `app/routes/integration.py`、`app/models/integration.py`，消费端 `Rehabman/backend/app/integrations/forms/`，试点记录 `docs/first-integration-pilot.md`。
本文只做设计，不修改任何代码。文中不含任何真实密钥或凭证值。

---

## ① 试点行为基线（现状，含 file:line 证据）

113.44 侧代码均在 `/mnt/acer-ssd/multiproject/康复问卷管理系统/`（下文简写为 113.44）。消费端代码在 `/mnt/acer-ssd/multiproject/Rehabman/`（下文简写为 RM）。

### 1.1 认证方式

- 服务端对服务端认证为 `Authorization: Bearer <client_id>.<secret>`，机器身份，不映射自然人权限（113.44 `app/routes/integration.py:53-55`）。消费端按同一格式构造请求头（RM `backend/app/integrations/forms/client.py:64-65`）。
- 解析规则：以 `.` 分隔为 `key_id.secret`，缺分隔符或缺任一段 → 401 `invalid_client`（integration.py:59-61）。
- 按 `client_id` 查库并用 `secrets.compare_digest` 比对哈希；查无或比对失败 → 401 `invalid_client`（integration.py:63-65；哈希与比对逻辑在 `app/models/integration.py:109-116`）。
- 客户端非 active 或已过 `expires_at` → 401 `client_unavailable`（integration.py:66-67；判定在 models/integration.py:81-86）。
- 每次成功认证都 `touch()` 更新 `last_used_at` 并提交（integration.py:68-69；字段在 models/integration.py:59）。无任何限流逻辑。

### 1.2 错误响应包络

- 统一 JSON：`{"success": false, "message": "...", "code": "<机器码>"}`（integration.py:45-46）。成功响应无 `success` 字段，直接返回业务对象。
- 消费端按 HTTP 状态分型：401/403 → `AuthorizationRejected`，网络错误 → `FormPlatformUnavailable`，其余 4xx/5xx → `FormPlatformError`，并解析远端 `code`/`message`（client.py:16-31、81-89）。消费端服务层把远端 4xx/5xx 统一映射为本地 502 透出（RM `backend/app/integrations/forms/service.py:36-48`）。

### 1.3 scope 校验逻辑（默认拒绝）

- 凭证范围存为 JSON：`{"project_ids": [...], "center_ids": [...], "questionnaire_ids": [...]}`（models/integration.py:55-56、71-79）。
- `allows()` 语义：三个维度任一为空或不在明确列表内即拒绝，**不沿用"空=不限"的旧语义**（models/integration.py:88-100，注释即原文）。
- 创建填报会话时在业务校验前先做 scope 检查，拒绝 → 403 `scope_denied`（integration.py:141-145）。
- 非空中心绑定：受试者 `center_id` 必须等于请求的 `center_id`，"未分中心"一律拒绝 → 403 `center_mismatch`（integration.py:158-160）。
- 服务凭证范围与操作者成员资格是两层独立校验：操作者必须是该项目该中心该表单的填报成员（`ProjectPermissionService.has_project_role`，FILL_ROLES 含项目管理/CRC/测试用户），否则 403 `operator_not_authorized`（integration.py:176-181；角色集合在 `app/services/project_permission_service.py:19-23`，方法签名在 :251）。
- 只返回/操作本客户端自己的资源：查询填报会话按 `client_id` 过滤（integration.py:212、224）；答卷只允许通过本客户端会话读取，防跨客户端枚举（integration.py:240-243）。

### 1.4 填报会话生命周期

- 状态机：`created → embedded → submitted`，旁路 `cancelled / expired`（models/integration.py:23-27）；过期在读取路径折叠（`effective_status`），不做写放大（models/integration.py:177-185）。
- TTL：默认 3600s，请求可传 `ttl_seconds`，钳制在 60s–8h（models/integration.py:206-208）。
- 嵌入令牌：`fs_` 前缀随机串，只存 SHA-256 哈希，明文只在创建响应出现一次（models/integration.py:20、37-40、209；integration.py:202-203 注释"明文只在创建响应中出现一次"）。
- embed 端点：令牌无效 404；过期/取消/客户端不可用/操作者不可用 410；已提交/令牌已用 409（integration.py:275-293）。委托会话只允许白名单端点（integration.py:35-41、410-422）。
- 取消：已过期 409 `session_expired`，已提交 409 `session_already_submitted`（integration.py:227-230）。
- 提交回执以服务端核验为准：只有 `response.subject_id/questionnaire_id/user_id` 与会话一致且 `status=submitted` 才绑定（integration.py:341-355）；消费端再核验 project/subject/questionnaire/operator 引用一致才确认（service.py:240-254）。

### 1.5 试点已覆盖与未覆盖的端点

已覆盖（全部在 integration.py）：`POST /integration/v1/fill-sessions`（:118）、`GET /integration/v1/fill-sessions/<uuid>`（:207）、`POST .../cancel`（:218）、`GET /integration/v1/responses/<id>`（:235）、`GET /integration/embed/<token>`（浏览器入口，:268）。

未覆盖（WP1 拟建，development-plan-2026-11-07.md:139）：项目目录、中心/受试者/表单目录、表单 definition、`GET /integration/v1/changes?cursor=...`（outbox 增量）均不存在。

### 1.6 试点答卷返回的现有字段

`GET /integration/v1/responses/{id}` 返回：`session_uuid, response_id, status, questionnaire_id, project_id, subject_id, fill_center_id, visit_code, visit_name, operator_user_id, submitted_at, updated_at, answers[{question_id, answer_text}]`（integration.py:251-265）。
答卷模型本身只有 `answer_text` 一个值字段，无单位、无缺失语义、无修订号、无评分（`app/models/questionnaire.py:1130-1140`）；Response 有 `draft/submitted/voided` 三态、`voided_at/void_reason`、`is_test_data`，但无修订号列（questionnaire.py:917-952）。

---

## ② OpenAPI 契约草案（API01 交付物，yaml）

设计要点先行说明，yaml 为契约正文：

- 所有路径挂在 `/integration/v1` 前缀下，破坏性变更走 `/integration/v2`，v1 内只做向后兼容新增（对应"版本化契约"）。
- 认证统一为 `integrationBearer`（Bearer `<client_id>.<secret>`，与试点一致，integration.py:53-70）。
- 分页统一为 cursor 模式：`limit`（1–200，默认 50）+ 不透明 `cursor`；响应统一带 `page` 对象（见 ③）。
- 目录接口的可见性 = 客户端 grant 范围 ∩ 资源归属，交集之外默认拒绝（不返回、不提示存在性差异以外的信息）。
- `changes` 为 API04 预留端点：契约先行冻结形状，实现落在 API04 的 outbox（见 ⑥）。

```yaml
openapi: 3.0.3
info:
  title: 113.44 康复问卷管理系统 — 受控集成 API
  version: 1.0.0-draft
  description: |
    供 Rehabman 等受控服务端调用的版本化契约。机器身份认证，默认拒绝；
    所有时间字段为 UTC ISO-8601 带 Z 后缀（与试点序列化一致，integration.py:111-113）。
servers:
  - url: https://{host}/integration
    variables:
      host: { default: TBD }   # 正式环境必须 HTTPS；试点仅回环 HTTP（integration.py:78-84）
security:
  - integrationBearer: []

tags:
  - name: directory     # API03 承接实现，本契约先冻结形状
  - name: forms
  - name: responses
  - name: changes       # API04 承接实现
  - name: fill-sessions # 试点已存在，按本契约补齐

paths:
  /v1/projects:
    get:
      tags: [directory]
      summary: 列出集成客户端被授权的项目
      operationId: listProjects
      parameters:
        - $ref: '#/components/parameters/limit'
        - $ref: '#/components/parameters/cursor'
      responses:
        '200':
          description: 授权范围内的项目（仅 grant 覆盖的项目可见）
          content:
            application/json:
              schema:
                type: object
                required: [data, page]
                properties:
                  data:
                    type: array
                    items: { $ref: '#/components/schemas/Project' }
                  page: { $ref: '#/components/schemas/PageInfo' }
        '401': { $ref: '#/components/responses/Unauthorized' }
        '403': { $ref: '#/components/responses/ScopeDenied' }
        '429': { $ref: '#/components/responses/RateLimited' }
        '503': { $ref: '#/components/responses/Unavailable' }

  /v1/projects/{project_id}/centers:
    get:
      tags: [directory]
      summary: 项目下授权可见的中心
      operationId: listCenters
      parameters:
        - $ref: '#/components/parameters/ProjectId'
        - $ref: '#/components/parameters/limit'
        - $ref: '#/components/parameters/cursor'
      responses:
        '200':
          description: grant 未覆盖该 project 时为空集或 403（按 403 语义执行）
          content:
            application/json:
              schema:
                type: object
                required: [data, page]
                properties:
                  data:
                    type: array
                    items: { $ref: '#/components/schemas/Center' }
                  page: { $ref: '#/components/schemas/PageInfo' }
        '401': { $ref: '#/components/responses/Unauthorized' }
        '403': { $ref: '#/components/responses/ScopeDenied' }
        '404': { $ref: '#/components/responses/NotFound' }
        '429': { $ref: '#/components/responses/RateLimited' }
        '503': { $ref: '#/components/responses/Unavailable' }

  /v1/projects/{project_id}/subjects:
    get:
      tags: [directory]
      summary: 项目下指定中心的受试者（必须显式给 center_id，未分中心默认拒绝）
      operationId: listSubjects
      parameters:
        - $ref: '#/components/parameters/ProjectId'
        - name: center_id
          in: query
          required: true
          schema: { type: integer, minimum: 1 }
          description: |
            必填且必须落在 grant 的 center_ids 内。不接受"空中心=全部"的语义：
            试点已明确空中心拒绝（integration.py:158-160，models/integration.py:88-100）。
        - name: status
          in: query
          schema: { type: string, enum: [screening, enrolled, completed, withdrawn, all], default: all }
        - $ref: '#/components/parameters/limit'
        - $ref: '#/components/parameters/cursor'
      responses:
        '200':
          content:
            application/json:
              schema:
                type: object
                required: [data, page]
                properties:
                  data:
                    type: array
                    items: { $ref: '#/components/schemas/Subject' }
                  page: { $ref: '#/components/schemas/PageInfo' }
        '401': { $ref: '#/components/responses/Unauthorized' }
        '403': { $ref: '#/components/responses/ScopeDenied' }
        '404': { $ref: '#/components/responses/NotFound' }
        '429': { $ref: '#/components/responses/RateLimited' }
        '503': { $ref: '#/components/responses/Unavailable' }

  /v1/projects/{project_id}/forms:
    get:
      tags: [forms]
      summary: 项目下授权可见的表单（含版本族与当前版本引用）
      operationId: listForms
      parameters:
        - $ref: '#/components/parameters/ProjectId'
        - name: status
          in: query
          schema: { type: string, enum: [active, closed, all], default: active }
          description: draft 与已删除表单永不返回（试点已按 active 过滤，integration.py:166-170）
        - $ref: '#/components/parameters/limit'
        - $ref: '#/components/parameters/cursor'
      responses:
        '200':
          content:
            application/json:
              schema:
                type: object
                required: [data, page]
                properties:
                  data:
                    type: array
                    items: { $ref: '#/components/schemas/FormSummary' }
                  page: { $ref: '#/components/schemas/PageInfo' }
        '401': { $ref: '#/components/responses/Unauthorized' }
        '403': { $ref: '#/components/responses/ScopeDenied' }
        '404': { $ref: '#/components/responses/NotFound' }
        '429': { $ref: '#/components/responses/RateLimited' }
        '503': { $ref: '#/components/responses/Unavailable' }

  /v1/forms/{form_id}/definition:
    get:
      tags: [forms]
      summary: 表单当前发布版本的定义快照（含 definition hash）
      operationId: getFormDefinition
      parameters:
        - $ref: '#/components/parameters/FormId'
        - name: version
          in: query
          required: false
          schema: { type: integer, minimum: 1 }
          description: 不传=当前发布版本；历史版本仅在 grant 与保留策略允许时返回
      responses:
        '200':
          content:
            application/json:
              schema: { $ref: '#/components/schemas/FormDefinition' }
        '401': { $ref: '#/components/responses/Unauthorized' }
        '403': { $ref: '#/components/responses/ScopeDenied' }
        '404': { $ref: '#/components/responses/NotFound' }
        '409':
          description: 表单存在但无已发布版本（questionnaire_inactive 语义，integration.py:169-170）
          content: { application/json: { schema: { $ref: '#/components/schemas/Error' } } }
        '429': { $ref: '#/components/responses/RateLimited' }
        '503': { $ref: '#/components/responses/Unavailable' }

  /v1/responses/{response_id}:
    get:
      tags: [responses]
      summary: 答卷结果（含修订、逐题原始值/单位/缺失、评分）
      operationId: getResponse
      parameters:
        - $ref: '#/components/parameters/ResponseId'
      responses:
        '200':
          content:
            application/json:
              schema: { $ref: '#/components/schemas/ResponseResult' }
        '401': { $ref: '#/components/responses/Unauthorized' }
        '403': { $ref: '#/components/responses/ScopeDenied' }
        '404':
          description: 不存在，或不在本客户端授权/会话范围内（试点已按 client 会话过滤，integration.py:240-243）
          content: { application/json: { schema: { $ref: '#/components/schemas/Error' } } }
        '410': { $ref: '#/components/responses/Gone' }
        '429': { $ref: '#/components/responses/RateLimited' }
        '503': { $ref: '#/components/responses/Unavailable' }

  /v1/changes:
    get:
      tags: [changes]
      summary: 变更事件增量（API04 outbox 游标读取；本契约先冻结形状）
      operationId: listChanges
      parameters:
        - $ref: '#/components/parameters/limit'
        - name: cursor
          in: query
          required: true
          schema: { type: string }
          description: 首次同步用初始化接口（API05）取得起始游标；游标过期返回 410 cursor_expired
        - name: event_types
          in: query
          schema:
            type: array
            items: { $ref: '#/components/schemas/ChangeEventType' }
            style: form
            explode: false
      responses:
        '200':
          content:
            application/json:
              schema:
                type: object
                required: [data, page]
                properties:
                  data:
                    type: array
                    items: { $ref: '#/components/schemas/ChangeEvent' }
                  page: { $ref: '#/components/schemas/PageInfo' }
        '401': { $ref: '#/components/responses/Unauthorized' }
        '403': { $ref: '#/components/responses/ScopeDenied' }
        '410':
          description: 游标过期（事件已超出保留窗口），须走 API05 受控重建
          content: { application/json: { schema: { $ref: '#/components/schemas/Error' } } }
        '429': { $ref: '#/components/responses/RateLimited' }
        '503': { $ref: '#/components/responses/Unavailable' }

  /v1/fill-sessions:
    post:
      tags: [fill-sessions]
      summary: 创建嵌入填报会话（试点已有，补齐契约）
      operationId: createFillSession
      requestBody:
        required: true
        content:
          application/json:
            schema: { $ref: '#/components/schemas/CreateFillSessionRequest' }
      responses:
        '201':
          content:
            application/json:
              schema: { $ref: '#/components/schemas/FillSession' }
        '400':
          description: invalid_json / invalid_parameters / invalid_origin（integration.py:123-139）
          content: { application/json: { schema: { $ref: '#/components/schemas/Error' } } }
        '401': { $ref: '#/components/responses/Unauthorized' }
        '403':
          description: scope_denied / center_mismatch / operator_not_authorized
          content: { application/json: { schema: { $ref: '#/components/schemas/Error' } } }
        '404':
          description: project/center/subject/questionnaire/operator_not_found
          content: { application/json: { schema: { $ref: '#/components/schemas/Error' } } }
        '409':
          description: subject_not_fillable / patient_unavailable / questionnaire_inactive
          content: { application/json: { schema: { $ref: '#/components/schemas/Error' } } }
        '410': { $ref: '#/components/responses/Gone' }
        '429': { $ref: '#/components/responses/RateLimited' }
        '503': { $ref: '#/components/responses/Unavailable' }

  /v1/fill-sessions/{session_uuid}:
    get:
      tags: [fill-sessions]
      summary: 查询填报会话状态（仅限本客户端创建的会话，integration.py:212）
      operationId: getFillSession
      parameters:
        - $ref: '#/components/parameters/SessionUuid'
      responses:
        '200':
          content: { application/json: { schema: { $ref: '#/components/schemas/FillSession' } } }
        '401': { $ref: '#/components/responses/Unauthorized' }
        '403': { $ref: '#/components/responses/ScopeDenied' }
        '404': { $ref: '#/components/responses/NotFound' }
        '429': { $ref: '#/components/responses/RateLimited' }
        '503': { $ref: '#/components/responses/Unavailable' }

  /v1/fill-sessions/{session_uuid}/cancel:
    post:
      tags: [fill-sessions]
      summary: 取消填报会话
      operationId: cancelFillSession
      parameters:
        - $ref: '#/components/parameters/SessionUuid'
      responses:
        '200':
          content: { application/json: { schema: { $ref: '#/components/schemas/FillSession' } } }
        '401': { $ref: '#/components/responses/Unauthorized' }
        '403': { $ref: '#/components/responses/ScopeDenied' }
        '404': { $ref: '#/components/responses/NotFound' }
        '409':
          description: session_expired / session_already_submitted（integration.py:227-230）
          content: { application/json: { schema: { $ref: '#/components/schemas/Error' } } }
        '429': { $ref: '#/components/responses/RateLimited' }
        '503': { $ref: '#/components/responses/Unavailable' }

components:
  securitySchemes:
    integrationBearer:
      type: http
      scheme: bearer
      description: |
        `Bearer <client_id>.<secret>`；机器身份，与自然人登录态隔离
        （integration.py:53-70）。secret 仅哈希存储，明文只在创建/轮换响应出现一次。

  parameters:
    limit:
      name: limit
      in: query
      schema: { type: integer, minimum: 1, maximum: 200, default: 50 }
    cursor:
      name: cursor
      in: query
      schema: { type: string }
      description: 不透明游标，客户端不得解析其内部结构；过期/非法返回 400 invalid_cursor 或 410 cursor_expired
    ProjectId:
      name: project_id
      in: path
      required: true
      schema: { type: integer, minimum: 1 }
    FormId:
      name: form_id
      in: path
      required: true
      schema: { type: integer, minimum: 1 }
    ResponseId:
      name: response_id
      in: path
      required: true
      schema: { type: integer, minimum: 1 }
    SessionUuid:
      name: session_uuid
      in: path
      required: true
      schema: { type: string, maxLength: 64 }

  responses:
    Unauthorized:
      description: 凭证缺失/格式错/无效（invalid_client）或已撤销/过期（client_unavailable）
      content: { application/json: { schema: { $ref: '#/components/schemas/Error' } } }
    ScopeDenied:
      description: 范围外资源或操作者无成员资格（默认拒绝，不区分"不存在"与"无权"以外细节）
      content: { application/json: { schema: { $ref: '#/components/schemas/Error' } } }
    NotFound:
      description: 资源不存在或不属于引用的父资源
      content: { application/json: { schema: { $ref: '#/components/schemas/Error' } } }
    Gone:
      description: 目标已永久失效（嵌入会话过期/取消、游标过期且不可续读）
      content: { application/json: { schema: { $ref: '#/components/schemas/Error' } } }
    RateLimited:
      description: 超出该客户端限流配额（API02 新增语义，试点无）
      content: { application/json: { schema: { $ref: '#/components/schemas/Error' } } }
    Unavailable:
      description: 平台维护或依赖不可用，客户端应按退避重试，不得当作业务失败
      content: { application/json: { schema: { $ref: '#/components/schemas/Error' } } }

  schemas:
    Error:
      type: object
      required: [success, message, code]
      properties:
        success: { type: boolean, const: false }
        message: { type: string, description: 人类可读描述，不含凭证材料 }
        code: { type: string, description: 机器码，见 ③ 错误码表 }
        details:
          type: object
          additionalProperties: true
          description: 可选结构化细节（如 retry_after、重建提示），不含敏感值

    PageInfo:
      type: object
      required: [limit, has_more]
      properties:
        limit: { type: integer }
        has_more: { type: boolean }
        next_cursor:
          type: [string, 'null']
          description: has_more=true 时必返回；客户端必须原样回传，不得拼接或改写

    Project:
      type: object
      required: [project_id, name, status]
      properties:
        project_id: { type: integer }
        name: { type: string }
        status: { type: string, enum: [active, closed] }
        source:
          $ref: '#/components/schemas/SourceRef'

    Center:
      type: object
      required: [center_id, project_id, name, status]
      properties:
        center_id: { type: integer }
        project_id: { type: integer }
        name: { type: string }
        status: { type: string, enum: [active, inactive] }

    Subject:
      type: object
      required: [subject_id, project_id, center_id, status]
      properties:
        subject_id: { type: integer }
        project_id: { type: integer }
        center_id:
          type: integer
          description: 非空；未分中心受试者不通过目录返回（默认拒绝，integration.py:158-160）
        status: { type: string, examples: [screening, enrolled, completed, withdrawn] }
        code:
          type: [string, 'null']
          description: 受试者编号（如已配置）；不做姓名等直标识符透出，最小化由 D06 决定

    SourceRef:
      type: object
      required: [system]
      description: 开发计划要求的"来源"字段（development-plan-2026-11-07.md:141）
      properties:
        system: { type: string, const: form-platform-11344 }
        environment: { type: string, examples: [production, pilot] }

    FormVersionRef:
      type: object
      required: [form_id, version, definition_sha256]
      description: |
        版本族/版本/定义 hash。113.44 已有承载模型：QuestionnaireFamily（family_id、
        revision，app/models/questionnaire_version.py:16-25）与 QuestionnaireVersion
        （sequence、state、definition_snapshot、snapshot_sha256，:52-62）；
        Questionnaire 上的 crf_code/crf_version 作为业务编码（app/models/questionnaire.py:45-46）。
      properties:
        form_id: { type: integer, description: questionnaire.id }
        family_id: { type: integer, description: questionnaire_family.id，版本族标识 }
        version: { type: integer, description: questionnaire_version.sequence，族内版本序号 }
        version_state: { type: string, enum: [draft, published, superseded] }
        definition_sha256: { type: string, maxLength: 64, description: 定义快照 SHA-256（snapshot_sha256） }
        crf_code: { type: [string, 'null'] }
        crf_version: { type: [string, 'null'] }

    FormSummary:
      type: object
      required: [form_id, project_id, title, status, current_version]
      properties:
        form_id: { type: integer }
        project_id: { type: integer }
        title: { type: string }
        status: { type: string, enum: [active, closed] }
        current_version: { $ref: '#/components/schemas/FormVersionRef' }

    FormDefinition:
      type: object
      required: [form, definition]
      properties:
        form: { $ref: '#/components/schemas/FormSummary' }
        definition:
          type: object
          description: 定义快照 JSON（问卷、题目、选项、显示条件、校验规则、单位、量表配置）
          properties:
            questionnaire_id: { type: integer }
            title: { type: string }
            questions:
              type: array
              items:
                type: object
                required: [question_id, question_type, order]
                properties:
                  question_id: { type: integer, description: 稳定字段编码的主键，消费端禁止按题目标题匹配 }
                  stable_code:
                    type: [string, 'null']
                    description: 跨版本稳定字段编码（Question.source_ref，app/models/questionnaire.py:621），由映射字典管理
                  question_type: { type: string }
                  order: { type: integer }
                  options: { type: [object, 'null'], description: 选项编码→标签，含编码级稳定 key }
                  unit: { type: [string, 'null'], description: 数值题单位语义 }
                  required: { type: boolean }
                  config: { type: [object, 'null'], description: 评分/量表等题目配置 }
            layout_bindings: { type: [object, 'null'], description: 表格槽位等非题目绑定（Response.layout_binding_values，questionnaire.py:943） }

    Answer:
      type: object
      required: [question_id]
      properties:
        question_id: { type: integer }
        stable_code: { type: [string, 'null'] }
        raw_value:
          description: 原始值；选项题为编码值，文本题为字符串；与展示文本分离
          type: [string, number, boolean, array, 'null']
        raw_text: { type: [string, 'null'], description: 原始填报文本（试点 answer_text 的直传，integration.py:247-250） }
        value:
          description: 标准化后的观察值（DATA02 消费）；契约预留，试点无此列
          type: [string, number, boolean, 'null']
        unit: { type: [string, 'null'], description: 数值单位；试点无此列（Answer 仅 answer_text，questionnaire.py:1136） }
        missing:
          type: [object, 'null']
          description: 缺失语义；试点无此结构
          properties:
            reason: { type: string, enum: [not_applicable, skipped, unknown, refused, condition_not_met] }
            display_conditions_met: { type: boolean }
        score:
          type: [object, 'null']
          description: 评分及人工覆盖来源；试点无此结构（评分未在 Answer/Response 上持久化）
          properties:
            value: { type: [number, string, 'null'] }
            source: { type: string, enum: [computed, manual_override], description: 人工覆盖必须标来源，不擅自重算（development-plan-2026-11-07.md:150） }
            overridden_by: { type: [integer, 'null'], description: 覆盖操作者 user_id }
            overridden_at: { type: [string, 'null'], format: date-time }
            rule_version: { type: [string, 'null'], description: 计算策略版本（questionnaire_calculation_policy） }

    ResponseResult:
      type: object
      required: [source, response_id, revision, project_id, center_id, subject_id, form, status, submitted_at, answers]
      properties:
        source: { $ref: '#/components/schemas/SourceRef' }
        response_id: { type: integer }
        result_code: { type: [string, 'null'], description: 平台内唯一结果码（questionnaire.py:927） }
        revision:
          type: integer
          minimum: 1
          description: |
            答卷修订号：提交=1，此后每次被授权的答案修改/评分变更/退回重填递增。
            试点与现库均无此列（questionnaire.py:924-956 无 revision），为 API04 前置新增字段，
            由 outbox 事件与修订写入路径共同维护。
        is_voided: { type: boolean, description: voided 状态映射；voided_at/void_reason 见下 }
        voided_at: { type: [string, 'null'], format: date-time }
        void_reason: { type: [string, 'null'] }
        is_test_data: { type: boolean, description: 试点/合成数据标记（questionnaire.py:952），消费端据此隔离 }
        project_id: { type: integer }
        center_id: { type: integer, description: fill_center_id；非空，未分中心答卷默认不透出 }
        subject_id: { type: integer }
        patient_archive_id: { type: [integer, 'null'] }
        form:
          allOf:
            - $ref: '#/components/schemas/FormVersionRef'
          description: 答卷实际所属的表单版本（响应属于具体版本，且版本族可追溯）
        visit_code: { type: [string, 'null'] }
        visit_name: { type: [string, 'null'] }
        status: { type: string, enum: [submitted, voided], description: draft 状态不对外透出 }
        operator_user_id: { type: [integer, 'null'], description: 真实操作者（代填关系保留，不写服务账号） }
        submitted_at: { type: [string, 'null'], format: date-time }
        updated_at: { type: [string, 'null'], format: date-time }
        layout_binding_values: { type: [object, 'null'] }
        answers:
          type: array
          items: { $ref: '#/components/schemas/Answer' }
        fill_session:
          type: [object, 'null']
          description: 若该答卷由集成会话产生，附会话引用（试点按 client 会话过滤，integration.py:240-243）
          properties:
            session_uuid: { type: string }
            ma_task_ref: { type: [string, 'null'], description: 发起方任务引用（models/integration.py:153-154） }

    ChangeEventType:
      type: string
      enum: [response.submitted, response.amended, response.scored, response.returned, response.voided, response.restored]
      description: 覆盖 API04 要求的全部答卷写入路径（提交、答案修改、评分变化、退回、作废/恢复）

    ChangeEvent:
      type: object
      required: [event_id, seq, occurred_at, event_type, subject_type, subject_id, revision]
      properties:
        event_id: { type: string, description: outbox 事件全局唯一 ID，消费端幂等键（DATA03） }
        seq: { type: integer, description: 单调递增序号，游标排序依据；同一事务内事件按序发布 }
        occurred_at: { type: string, format: date-time }
        event_type: { $ref: '#/components/schemas/ChangeEventType' }
        subject_type: { type: string, const: response }
        subject_id: { type: integer }
        revision: { type: integer, description: 事件对应的答卷修订号 }
        payload_ref:
          type: object
          description: 事件只带引用，正文由 /v1/responses/{id} 拉取（避免事件体膨胀与敏感值重复扩散）
          properties:
            project_id: { type: integer }
            center_id: { type: integer }
            form_id: { type: integer }
            form_version: { type: integer }
            definition_sha256: { type: string }

    CreateFillSessionRequest:
      type: object
      required: [operator_user_id, project_id, center_id, subject_id, questionnaire_id, allowed_origin]
      properties:
        operator_user_id: { type: integer, description: 真实操作者，服务凭证不能替代成员授权（integration.py:176-181） }
        project_id: { type: integer }
        center_id: { type: integer, description: 非空，且必须与受试者归属中心一致（integration.py:158-160） }
        subject_id: { type: integer }
        questionnaire_id: { type: integer }
        allowed_origin: { type: string, format: uri, description: 必须 HTTPS（隔离验证允许回环 HTTP，integration.py:73-84） }
        questionnaire_version_ref: { type: [string, 'null'], description: 指定版本引用；正式接入建议改传 family_id+version，与 FormVersionRef 对齐 }
        visit_code: { type: [string, 'null'] }
        visit_name: { type: [string, 'null'] }
        ma_task_ref: { type: [string, 'null'], maxLength: 160 }
        ttl_seconds: { type: [integer, 'null'], minimum: 60, maximum: 28800, description: 钳制规则见 models/integration.py:206-208 }
        idempotency_key:
          type: [string, 'null']
          maxLength: 128
          description: 新增。同一客户端+key 在会话存活期内重复调用返回既有会话（防重复请求，试点验收项之一）

    FillSession:
      type: object
      required: [session_uuid, status, project_id, center_id, subject_id, questionnaire_id, expires_at]
      properties:
        session_uuid: { type: string }
        status: { type: string, enum: [created, embedded, submitted, cancelled, expired] }
        project_id: { type: integer }
        center_id: { type: integer }
        subject_id: { type: integer }
        questionnaire_id: { type: integer }
        questionnaire_version_ref: { type: [string, 'null'] }
        visit_code: { type: [string, 'null'] }
        visit_name: { type: [string, 'null'] }
        ma_task_ref: { type: [string, 'null'] }
        operator_user_id: { type: integer }
        response_id: { type: [integer, 'null'] }
        expires_at: { type: string, format: date-time }
        created_at: { type: [string, 'null'], format: date-time }
        submitted_at: { type: [string, 'null'], format: date-time }
        embed_url: { type: [string, 'null'], description: 仅创建响应返回 }
        embed_token:
          type: [string, 'null']
          writeOnly: true
          description: 仅创建响应返回一次；服务端只存哈希（models/integration.py:20、37-40）
```

---

## ③ 错误码与分页/游标语义

### 3.1 错误码表（code → HTTP）

| HTTP | code | 语义 | 试点现状 |
|---|---|---|---|
| 400 | `invalid_client`（仅格式错时归 401，此处不适用） | — | — |
| 400 | `invalid_json` | 请求体不是 JSON 对象 | 已有，integration.py:123-125 |
| 400 | `invalid_parameters` | 必填整数缺失或非整数 | 已有，integration.py:132-134 |
| 400 | `invalid_origin` | `allowed_origin` 非 HTTPS（隔离验证回环除外） | 已有，integration.py:136-139 |
| 400 | `invalid_cursor` | 游标格式非法/被篡改 | 新增（changes/分页） |
| 401 | `invalid_client` | 缺 Bearer、格式错、client_id 不存在、secret 不匹配 | 已有，integration.py:57-65 |
| 401 | `client_unavailable` | 客户端已撤销或已过期 | 已有，integration.py:66-67 |
| 403 | `scope_denied` | 凭证 grant 不覆盖请求的 project/center/questionnaire 任一维度 | 已有，integration.py:141-145 |
| 403 | `center_mismatch` | 受试者未分中心或与指定中心不一致 | 已有，integration.py:158-160 |
| 403 | `operator_not_authorized` | 操作者无该中心+表单的填报成员资格 | 已有，integration.py:176-181 |
| 404 | `project_not_found` / `center_not_found` / `subject_not_found` / `questionnaire_not_found` / `operator_not_found` | 资源不存在、不属于父资源或状态不满足（项目非 active、中心停用等归 404，与试点一致） | 已有，integration.py:147-174 |
| 404 | `session_not_found` / `response_not_found` | 会话/答卷不存在，或不在本客户端授权范围内（不区分二者，防枚举） | 已有，integration.py:212-214、240-246 |
| 409 | `subject_not_fillable` / `patient_unavailable` | 受试者状态不可填报 / 无有效患者档案 | 已有，integration.py:161-164 |
| 409 | `questionnaire_inactive` | 表单非 active | 已有，integration.py:169-170 |
| 409 | `session_expired` / `session_already_submitted` | 取消已过期/已提交的会话 | 已有，integration.py:227-230 |
| 409 | `definition_not_published` | 表单存在但无发布版本（definition 接口） | 新增（复用 questionnaire_inactive 判定） |
| 410 | `session_gone` | 嵌入会话已过期/取消/客户端或操作者已失效（浏览器 embed 入口现有语义的 API 化） | 部分已有（embed 端点 410，integration.py:280-293）；API 化新增 |
| 410 | `cursor_expired` | changes 游标超出事件保留窗口，须走 API05 重建 | 新增，API04/05 预留 |
| 429 | `rate_limited` | 超出客户端限流配额；`details.retry_after` 给秒数 | 新增（试点无任何限流，integration.py:53-70 仅有 touch） |
| 503 | `service_unavailable` | 平台维护/依赖不可用；不携带业务细节，客户端按退避重试 | 新增（消费端已把 5xx 映射为 FormPlatformUnavailable 类语义，client.py:26-28） |

设计约定：

- 401 只用于凭证本身的问题；范围问题一律 403，资源问题一律 404，与试点分层一致。
- 404 对"不存在"与"不在授权范围"返回同一 code（`session_not_found`/`response_not_found`），避免通过错误差异枚举他方资源（试点已如此，integration.py:242-243 注释）。
- 410 保留给"永久失效、重试无意义"的场景（会话终结、游标过期），与 409（可随状态变化恢复）区分。
- 错误响应不含凭证、不含完整答卷内容；消费端已保证凭证不进日志（client.py:6）。

### 3.2 分页与游标

- 参数：`limit`（1–200，默认 50）、`cursor`（不透明，原样回传）。
- 排序：目录类按 `(created_at, id)` 稳定排序；`changes` 按 outbox `seq` 单调排序。翻页期间数据变更不产生重复或遗漏条目（重复可容忍，遗漏不允许——与 DATA03 幂等消费配合）。
- 响应 `page`：`{limit, has_more, next_cursor}`；`has_more=false` 时 `next_cursor=null`。目录类游标过期/非法 → 400 `invalid_cursor`；`changes` 游标因事件保留窗口过期 → 410 `cursor_expired`（必须受控重建，不允许客户端重置为 0 造成漏读，对应 API05）。
- 约束：单一方向前进（不支持任意页跳转），游标有效期内数据可重复读（消费端以 `event_id` 幂等去重）。

### 3.3 权限校验语义（API02 范围校验的契约化）

1. **scope 覆盖判定**：请求涉及的 `(project_id, center_id, questionnaire_id)` 三元组必须同时落在 grant 的三个列表内；任一缺失或不在列表内即 `scope_denied`（试点语义，models/integration.py:88-100）。目录接口同规则：项目列表=grant.project_ids 交集；centers/forms 同理；subjects 必须显式 center_id 且在 grant 内。
2. **默认拒绝**：空 grant 列表 = 不允许任何资源，不是"不限"；新客户端未授权前所有目录/数据接口返回空集或 403（试点注释明确废弃"空=不限"旧语义，models/integration.py:88-89）。
3. **未分中心拒绝**：受试者/答卷 `center_id` 为空时不透出、不可发起填报；绑定中心必须一致（integration.py:158-160）。是否放开由机构显式扩大 grant，而非接口侧默认放行。
4. **凭证授权 ≠ 操作者授权**：服务凭证范围是外层必要条件；填报类操作还要求数据库会话绑定的真实操作者具备 `FILL_ROLES` 成员资格（integration.py:176-181）。两层独立校验，缺一即拒。
5. **资源归属链校验**：center∈project、subject∈project 且 subject.center=center、questionnaire∈project、operator 存在且 active，逐层拒绝（integration.py:147-174）。
6. **撤权即时性**：每次请求都重查 `IntegrationClient.is_usable()`（integration.py:63-67），不缓存凭证判定；会话读取路径也校验 client 可用（integration.py:288-289、326-333）。AUTH04 的授权版本号（见 ⑤）用于消费端本地缓存的失效加速。

---

## ④ 字段覆盖对照表（开发计划 development-plan-2026-11-07.md:141 要求 → 试点现状）

| 契约字段组 | 试点现状 | 证据 | 差口与去向 |
|---|---|---|---|
| 来源（source） | **缺**。响应无来源标识字段 | integration.py:251-265 无此字段 | 新增 `source`（SourceRef），目录/答卷/事件统一携带 |
| 项目/中心/受试者 | **已覆盖**（IDs + fill_center_id） | integration.py:100-103、255-258 | 目录接口为新增端点；字段本身无差 |
| 表单版本族/版本 | **部分**。会话有 `questionnaire_version_ref` 自由字符串；Questionnaire 有 `crf_code/crf_version`；版本族模型（QuestionnaireFamily/QuestionnaireVersion）已存在但集成 API 未暴露 | integration.py:105、195；questionnaire.py:45-46；questionnaire_version.py:16-62 | 新增 `FormVersionRef`（family_id/version/definition_sha256），`questionnaire_version_ref` 建议对齐为 family+version |
| 定义 hash | **模型已有、契约缺**。`QuestionnaireVersion.snapshot_sha256` 已持久化 | questionnaire_version.py:59-60 | definition 接口直接读该列，几乎零成本 |
| 答卷 ID | **已覆盖**（response_id、result_code 模型已有） | integration.py:253；questionnaire.py:927 | 无差 |
| 答卷修订号（revision） | **缺**。Response 无修订号列，答案修改即覆盖 `answer_text` | questionnaire.py:924-956（无 revision）；Answer 仅 answer_text+updated_at（:1130-1140） | 新增 revision 列与递增规则；是 API04 事件序的前置 |
| 访视 | **已覆盖**（visit_code/visit_name，会话与答卷两侧都有） | integration.py:106-107、259-260；questionnaire.py:950-951 | 无差 |
| 状态/时间 | **部分**。status/submitted_at/updated_at 已有；voided_at/void_reason 模型有但响应未透出；draft 不透出的规则需固化 | integration.py:254、262-263；questionnaire.py:938、947-949 | 补 is_voided/voided_at/void_reason/is_test_data |
| 题目与原始值 | **部分**。`answers[{question_id, answer_text}]` 只有展示文本，无选项编码级原始值、无 stable_code | integration.py:247-250；questionnaire.py:1136 | raw_value（编码）/raw_text 分离；stable_code 接 `Question.source_ref`（questionnaire.py:621） |
| 单位/缺失语义 | **缺**。Answer 无 unit/missing 列；定义侧 Question.config 有空间但契约未约定 | questionnaire.py:1130-1140 | 新增 Answer.unit 与 missing 结构；单位口径随 FORM02 确认 |
| 评分及人工覆盖来源 | **缺**。评分未在答卷侧持久化，无覆盖来源记录 | questionnaire.py 全文无 score 列 | 新增 Answer.score{value,source,overridden_by,rule_version}；计算策略模型 `questionnaire_calculation_policy.py` 已存在可挂接 |
| 填报会话绑定（操作者/任务/来源/有效期） | **已覆盖**，是试点最完整部分 | integration.py:118-204；models/integration.py:126-164 | 补 `idempotency_key` 防重复创建 |
| 防跨客户端枚举 | **已覆盖** | integration.py:212、224、240-243 | 无差 |
| 错误码/错误包络 | **部分**。包络与多数 code 已有；410/429/503 及 cursor 类 code 缺 | integration.py:45-46 及各分支 | 见 ③ 表 |
| 分页 | **缺**。所有现有端点无分页参数 | integration.py:207-265 全文无 limit/cursor | 统一 limit+cursor（③.2） |

---

## ⑤ IntegrationClient / Grant 正式化设计（API02）

### 5.1 现状与差口

试点 `IntegrationClient`（models/integration.py:43-123）：`client_id`、`secret_hash`（SHA-256 无盐）、`scopes_json`（三列表 JSON）、`status`（active/revoked 二值）、`expires_at`、`last_used_at`。缺：吊销时间戳、轮换机制、限流配置、授权版本号、grant 级独立生命周期、创建/变更审计。

### 5.2 目标模型

```
IntegrationClient            IntegrationGrant              IntegrationGrantAudit
  id                           id                            id
  client_id (unique)           client_id -> client           client_id
  name                         scope_type: project|center|questionnaire
  status: active|revoked       target_id                     action: created|rotated|
  secret_hash (加盐哈希)        status: active|revoked                |revoked|scope_changed|
  secret_created_at            expires_at                     |rate_changed
  secret_previous_hash (可选,   revoked_at                    actor_user_id
    轮换重叠期双活用)            granted_by_user_id            before_json / after_json
  auth_version (int)           rate_limit_per_minute         created_at
  status_changed_at            created_at / updated_at
  revoked_at
  rate_limit_per_minute (客户端级兜底)
  created_by_user_id
  created_at / updated_at
  last_used_at / last_used_ip
```

要点：

- **scope 模型从 JSON 列升级为 Grant 行**：每行一个 `(scope_type, target_id)`。项目粒度 grant 授整个项目（含该项目全部中心/表单）；中心粒度授予指定中心；表单粒度授予指定 questionnaire。`allows()` 改为"任一 grant 行命中即可"，保持默认拒绝：无任何 grant 命中即 `scope_denied`。兼容期可保留 `scopes_json` 读取并在迁移脚本中折算成 Grant 行（试点三列表结构 models/integration.py:71-79 可无损映射）。
- **为什么不用 Partner AI 凭证**：`PartnerAIApiCredential`（app/models/partner_ai.py:42-57）是计费账号下的 LLM 网关密钥（scopes 形如 `chat.completions,models,billing.read`，:52），语义、生命周期、审计对象都不同。IntegrationClient 保持独立表、独立 client_id 命名空间、独立 scope 词表（`project/center/questionnaire` 资源粒度，非 API 能力粒度），杜绝凭证混用导致的授权串台。开发计划完成标准亦明确"不复用 Partner AI 密钥"（development-plan-2026-11-07.md:133）。
- **授权版本号 `auth_version`（供 AUTH04）**：client 级单调整数，任何 grant 增删改、吊销、轮换、限流变更时 +1。同时在 `FillSession` 上快照创建时的 `auth_version`；委托会话守卫（integration.py:320-338）在版本不一致时立即失效会话。消费端在每次同步/确认调用时回读版本号，不一致即丢弃本地授权快照并重新拉取目录——这满足 AUTH04"身份和授权版本、失效通知、缓存有效期策略"的完成标准（development-plan-2026-11-07.md:123）。版本号变更同时写 `IntegrationGrantAudit`，供对账。
- **到期**：保留 `expires_at`（client 级）；grant 级各带 `expires_at`，`is_usable()` 扩展为 client 未过期 ∧ 至少一条未过期 active grant（现行判定 models/integration.py:81-86 只看 client）。
- **吊销**：`status=revoked` + `revoked_at`（试点只有状态位，无时间，models/integration.py:48-49、57）。吊销即时生效：现有每请求重查机制（integration.py:63-67）不变；进行中的 FillSession 经 `effective_status`/守卫路径（integration.py:288-289、326-333）已校验 client 可用性，加入 auth_version 后更早失效。
- **轮换**：新增 rotate 语义——生成新 secret，旧 secret 可配置一个重叠窗口（0–24h，默认 0）内双活（`secret_previous_hash`），窗口过后旧 secret 校验失败并返回 401 `invalid_client`。secret 明文仅在创建/轮换响应出现一次（与试点嵌入令牌同一策略，models/integration.py:37-40；试点验收记录 first-integration-pilot.md:33"集成客户端密钥仅哈希存储、明文仅创建时出现一次"）。哈希算法升级：试点为无盐 SHA-256（models/integration.py:109-113），正式版改为加盐慢哈希（PBKDF2/scrypt），`verify_secret`（:115-116）同步升级；旧哈希在轮换时迁移。
- **限流**：client 级 `rate_limit_per_minute` + grant 级可选覆盖；计数用内存/Redis 滑动窗口即可，超限返回 429 `rate_limited` + `retry_after`。限流失败开放（fail-open 或 fail-closed）由 D11 的"授权状态不可用处理"决策统一，默认建议 fail-closed（只挡集成面，不影响本系统人工使用）。
- **审计**：所有 grant 变更走 `IntegrationGrantAudit`（对应 AUTH02"知情授权与操作审计"，development-plan-2026-11-07.md:121）。

### 5.3 试点 IntegrationClient 需要升级的字段清单

| 升级项 | 现状 | 目标 |
|---|---|---|
| secret 哈希 | 无盐 SHA-256（models/integration.py:109-116） | 加盐慢哈希 + `secret_created_at` + 轮换双活字段 |
| scope | 三列表 JSON 单列（models/integration.py:55-56） | IntegrationGrant 行表（project/center/questionnaire 粒度），JSON 列迁移期兼容 |
| 吊销 | 仅 status 位，无 revoked_at（models/integration.py:48-49、57） | status + revoked_at + 变更审计 |
| auth_version | 无 | client 级版本号；FillSession 快照并即时校验 |
| 限流 | 无（每请求只 touch，integration.py:68-69） | client/grant 级 rate_limit_per_minute + 429 语义 |
| grant 生命周期 | 到期只有 client 级 expires_at（models/integration.py:58） | grant 级 expires_at/revoked_at/granted_by |
| 审计 | 无 | IntegrationGrantAudit 全动作记录 |
| 操作者映射 | operator_user_id 由消费端明文传入（integration.py:127） | 保留，但校验端补 AUTH04 授权版本联动（操作者停用/撤权即时失效，integration.py:172-174、291-293 已有基线） |

---

## ⑥ 与 API04/API05 outbox 的衔接预留

- **事件发布在事务内**：API04 的 outbox 行与答卷写入同事务提交（回滚即无事件，完成标准 development-plan-2026-11-07.md:135）。本契约的 `ChangeEvent.seq` 即 outbox 自增序号；`GET /v1/changes` 只读 outbox，不查业务表，保证游标推进与数据变更解耦。
- **事件类型枚举**已按 API04 覆盖面冻结（`response.submitted/amended/scored/returned/voided/restored`）；`amended/scored` 依赖 ④ 中新增的 `revision` 列与评分持久化，否则无法区分"修改后的事件"与重复提交。
- **事件体只带引用**（`payload_ref`），正文由 `GET /v1/responses/{id}` 按需拉取：答卷结果接口的权限语义（本客户端授权范围 + 404 防枚举，③.3）同样约束事件消费，事件不成为绕过 grant 的旁路。
- **游标语义与 API05 对接**：初始化（API05）返回一个与 outbox 一致的起始游标，保证"初始化期间并发提交不丢"——快照取到 seq=N，则 changes 从 N+1 起；游标过期返回 410 `cursor_expired`，重建走 API05 的对账/重放，而不是客户端自行重置游标。
- **消费端预留**：RM 侧 `SyncCursor/SyncRun`（development-plan-2026-11-07.md:156 拟建模型）存 `event_id`（幂等键）与 `seq`；乱序/重复按 DATA03 约定处理。现有 `IntegrationFillTask.confirm` 的远端引用一致性核验（service.py:240-254）在事件通道下同样适用：事件回放的答卷也须核验 project/subject/questionnaire/operator 引用。
- **填表会话与事件的关系**：FillSession 提交（integration.py:341-355 绑定 response）在 API04 中应产生 `response.submitted` 事件，与现有 `_attach_submitted_response` 路径共用同一 outbox 写入点，避免"会话确认可见、事件流却漏发"的双通道不一致。

---

## 附：证据文件索引

- 113.44 `/mnt/acer-ssd/multiproject/康复问卷管理系统/app/routes/integration.py`（认证、错误包络、scope、会话、embed、委托守卫）
- 113.44 `/mnt/acer-ssd/multiproject/康复问卷管理系统/app/models/integration.py`（IntegrationClient、FillSession）
- 113.44 `/mnt/acer-ssd/multiproject/康复问卷管理系统/app/models/questionnaire.py`（Response/Answer/Questionnaire，:909、:1122、:20）
- 113.44 `/mnt/acer-ssd/multiproject/康复问卷管理系统/app/models/questionnaire_version.py`（QuestionnaireFamily/QuestionnaireVersion，:16、:40）
- 113.44 `/mnt/acer-ssd/multiproject/康复问卷管理系统/app/models/partner_ai.py`（PartnerAIApiCredential，:42）
- 113.44 `/mnt/acer-ssd/multiproject/康复问卷管理系统/app/services/project_permission_service.py`（FILL_ROLES :19-23、has_project_role :251）
- RM `/mnt/acer-ssd/multiproject/Rehabman/backend/app/integrations/forms/client.py`（消费端错误分型）
- RM `/mnt/acer-ssd/multiproject/Rehabman/backend/app/integrations/forms/service.py`（任务确认与一致性核验）
- RM `/mnt/acer-ssd/multiproject/Rehabman/backend/app/integrations/forms/models.py`（本地任务模型与状态机）
- RM `/mnt/acer-ssd/multiproject/Rehabman/docs/development-plan-2026-11-07.md`（WP1 :128-141、AUTH04 :123、DATA03 :151）
- RM `/mnt/acer-ssd/multiproject/Rehabman/docs/first-integration-pilot.md`（试点验收与局限）
