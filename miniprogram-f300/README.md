# Rehabman 微信小程序

使用原生微信小程序承接 F300 的蓝牙连接和手动心率采集，并通过当前登录账号将读数交给 Rehabman 服务端。界面只同步用户手动确认的一条实时心率；没有定时后台采集，也不调用设备设置和 OTA。

患者端提供康复方案及反馈、健康档案、日常记录、随访和知情同意；医护端提供患者工作台、随访和问卷任务。双方可在已核实的管理关系内使用消息，关系解除后保留历史但不能发送。宣教内容来自已发布的康复方案，签署记录不代表电子签名认证。

## 接入配置

1. `miniprogram/config.js` 当前指向已确认的测试服务器 HTTPS IP 地址及 `/medical/api`；此配置用于开启调试后的测试。正式使用前需要换成合规域名并完成微信后台配置。
2. `project.config.json` 当前使用用户提供的测试 AppID `wxcdfbfc3bc5a445fa`。真机蓝牙需要开发者工具权限和微信账号权限。系统域名也要登记到小程序 request 合法域名。
3. 使用微信开发者工具打开本目录。开发者工具模拟器不提供真实 BLE 测试；请在 iPhone 微信真机上调试。

## 登录和权限

页面先请求 `/auth/config`。在 `mode=oidc` 时，小程序使用微信安全随机数生成 32 字节 PKCE verifier，只把 SHA-256 challenge 交给 `POST /auth/mini/transactions`；verifier 只留在当前页面内存，并通过 JSON POST 用于轮询、兑换或取消，不写入 URL 或本地存储。WebView 由系统服务器完成现有 OneID 登录；小程序只信任服务端事务状态，不读取 WebView 消息中的登录凭据。轮询期间将 `pending`、`oidc_started`、`awaiting_confirmation` 视为处理中状态。进入 `ready` 后先显示 OneID 账号和角色，用户确认后才兑换一次性 mini Bearer 会话；兑换后再通过 `/users/me` 核对账号和角色，用户第二次确认后才加载患者和设备数据。mini 凭据只存当前运行内存，退出、会话失效或短时会话到期后清除，并调用服务端撤销接口。当前服务器使用何种模式由运行配置决定。

在 `mode=legacy` 时，为兼容尚未迁移的服务器，仍可使用 OAuth2 表单 `/users/login`；服务切换到 OneID 后该路径不可用。小程序不会在 OneID 模式尝试遗留密码接口。

患者使用 `/users/me` 和不带 `patient_id` 的 `/devices/` 查询，后端负责将账号映射到患者实体。医生和健康管理师从各自已授权患者清单选择对象。管理员不开放患者选择。无 F300 绑定时，用户可在已认证设备后明确确认绑定；patient_id 只由医护端显式传入，患者端由服务端推导。

## 同步契约

手环通过 Veepoo SDK 返回 type 1 认证信息和 type 51 实时心率回调。type 1 的 `VPDeviceMAC` 仅作为服务端匹配用的候选关联标识；本次 F300 测试确认该字段非空，但跨重连、跨手机的稳定性及防伪能力尚未验证。小程序不会把 iOS 扫描得到的临时 `deviceId` 当作硬件身份。绑定新设备时由用户确认设备与患者的关联，服务端保存此 claim 并在读数上传时再次校验；这属于账号授权和标识匹配，不是密码学设备持有证明。

每条读数的 `measured_at` 是小程序收到 type 51 回调时的手机本地时间及 UTC offset，`raw_payload.capture_time_source` 明示时间来源。用户结束测量后确认属于所选患者，再向 `POST /devices/{device_id}/veepoo/readings` 提交 `{hardware_id, readings:[...]}`。服务端从用户会话和绑定关系推导患者，不接受客户端患者身份作为事实来源，按既有 ingestion 管道校验、去重并写入设备数据与健康数据。

失败或拒绝时，待上传读数留在当前页面内存中，可核对后重试；成功或服务端确认重复后清除。读数不会持久化到微信本地存储，因此退出或重启会丢失未上传数据。此版本没有安全离线队列。OneID mini 会话仅在内存中；兼容模式的 legacy access token 沿用既有微信本地存储。不保存密码，不提供本地密码刷新接口。

## 验证

在项目目录运行：

```sh
node --test tests/*.test.cjs
```

mock 测试覆盖登录、账号切换、患者页面和心率采集等流程。用户此前已在 iPhone 上完成 OneID 登录，并使用 Veepoo 厂商 demo 连接 F300（固件 `00.37.03.00-5272`）取得心率值；这不代表新增页面和读数上传已经完成真机验收，也不证明医疗准确性。

## 厂商 SDK

`miniprogram/libs/veepoo/` 中的 bundle 和类型声明来自 `HBandSDK/WeChat_Mini_Program_Ble_SDK`，commit `ad2f60c258fa09f7f3d34cdeb2e32b8baf7664dd`（V1.2.1）。其 Apache-2.0 许可证副本见 `LICENSE-Veepoo-Apache-2.0`，来源与兼容性范围见 `THIRD_PARTY.md`。SDK 仓库声明其公版仅用于 Veepoo 穿戴设备；具体型号兼容和指标授权仍需厂商确认。
