# 隔离演示账号初始化

普通 `start.sh` 启动只连接数据库，不再自动创建管理员、医生、健康管理师或患者。所有账号（包括演示账号）的登录都使用数据库中的密码哈希，邮箱与预设密码不能绕过哈希校验。已更换哈希后，旧演示密码不再有效；停用账号也不能登录。

## 创建独立演示环境

先准备仅供合成数据使用的本地 MongoDB。初始化必须显式提供字面回环地址和端口，数据库名称以 `medicalassistant_demo_` 开头，并带至少8位独立后缀。工具拒绝已有任何集合的数据库、远程地址、DNS/SRV、凭证、URI参数或副本集种子列表，不读取默认数据库作为写入目标。

从项目根目录执行，例如使用一个**全新**数据库名：

```bash
cd backend
DEBUG=false .venv/bin/python -m app.tools.seed_demo \
  --mongo-url mongodb://127.0.0.1:37020 \
  --database medicalassistant_demo_20261107_local
cd ..
DEBUG=false MONGODB_URL=mongodb://127.0.0.1:37020 \
  MONGODB_DB_NAME=medicalassistant_demo_20261107_local ./start.sh
```

完成后使用项目 `./stop.sh` 停止前后端；数据库服务仍由原持有方管理。

| 演示角色 | 合成账号 | 演示密码 |
|---|---|---|
| 管理员 | admin@example.com | Admin123! |
| 医生 | doctor@example.com | Doctor123! |
| 健康管理师 | liujk@example.com | Manager123! |
| 患者 | zhangsan@example.com | Patient123! |
| 测试患者 | test@example.com | password123 |

这些公开演示凭据仅适用于隔离合成数据，不可用于真实患者环境。前端开发模式展示的演示快捷入口不会自行创建账号。

## 现有数据与边界

重复初始化会拒绝，不会重设已有用户的密码。初始化失败会留下可审查的 `demo_seed_manifest`；选择新的隔离数据库，不要通过重置现有账号来恢复。

此变更不删除或停用历史账号、不清理任何既有数据库。历史自动创建的账号及其旧会话需要先核实来源和实际使用，再执行经授权的处置。已有访问令牌不会仅因密码哈希变化而自动失效；账号停用后当前认证会拒绝其访问，完整凭据变更/会话撤销仍属于统一身份改造。

113.44 继续是目标账号权威，以上工具只保障本地开发演示与真实数据分离，不代表已完成统一登录或多中心授权。
