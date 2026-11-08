# 本地 MongoDB 副本集

用于本项目的独立本地开发数据库，支持多文档事务。单节点副本集提供事务能力，**不提供高可用**。宿主机发布端口绑定回环地址；`mongod --bind_ip_all` 仍监听容器网络，同一 Docker 网络中的容器可无认证访问，不能把回环端口发布视为完整网络隔离。该配置适用于受控本机开发；正式部署需另行配置账号、网络隔离、备份和副本集成员。

## 新建数据库

```bash
./deploy/mongodb/start.sh
```

默认使用 `mongo:7.0.16`、独立 Compose 项目 `rehabman-mongodb`、命名卷 `rehabman-mongodb_data`，端口 `127.0.0.1:37021`。端口冲突时启动失败，不会停止占用端口的服务。可在首次启动时以 `REHAB_MONGO_PORT=其他端口` 指定端口；后续启停保持相同设置。

应用连接设置：

```dotenv
MONGODB_URL=mongodb://127.0.0.1:37021/?replicaSet=rehab_rs&directConnection=true
MONGODB_DB_NAME=rehabman_dev
```

`directConnection=true` 用于本机映射端口；容器内成员地址是 `127.0.0.1:27017`。此 URI 不适用于跨机器部署。应用仍用仓库根目录 `./start.sh`、`./stop.sh` 启停；应用脚本不管理数据库生命周期。

```bash
./deploy/mongodb/stop.sh
```

停止保留数据卷。重启时初始化脚本核对既有副本集配置，匹配则复用，遇到不同配置拒绝重配。

## 验证

```bash
docker compose -f deploy/mongodb/compose.yml exec -T mongo mongosh --quiet --eval 'db.hello()'
```

必须同时看到 `setName: 'rehab_rs'` 和 `isWritablePrimary: true`。`ping` 成功只证明可连接，不证明事务能力。业务验收还需运行真实副本集上的事务提交、回滚、并发和幂等测试。

在新建、仅含合成测试数据的本地实例上运行随访事务测试：

```bash
cd backend
DEBUG=false REHAB_TEST_REPLICA_URI='mongodb://127.0.0.1:37021/?replicaSet=rehab_rs&directConnection=true' \
  .venv/bin/python -m pytest tests/test_followup_transactions_mongo.py -q
```

测试为每个用例新建 `rehab_txn_` 前缀随机库，结束后删除。不要指向业务实例。缺少该环境变量时，真实数据库测试会明确跳过；普通内存测试通过不能替代这些结果。

## 既有数据库接入边界

本配置创建新实例，不转换或挂载已有 MongoDB 数据目录。既有数据库迁移应先核实拓扑和实际路径，在受控数据副本上演练备份恢复及兼容性，再安排停写、最终备份、迁移与业务验证。不可直接把其他实例的数据目录挂到此配置，也不可因需要事务而在应用中降级为非事务写入。

## 本轮隔离验证

2026-11-08 在独立 `mongo:7.0.16` 临时容器、tmpfs 数据和合成库中验证了 `hello` 返回副本集主节点、真实事务提交以及异常后的全量回滚；随访真实数据库测试 8 项通过（副本集 7 项、standalone 1 项）。standalone 临时实例上的取消并改期返回 `503 / FOLLOWUP_TRANSACTION_UNAVAILABLE`，原节点、节点总数与时间线均未改变。另以本目录配置和独立临时 Compose 项目实测首次启动、重复启动、主节点选举、跨集合事务回滚及停止流程，并清理该测试项目容器、卷和网络。测试结论不代表现有业务数据库已迁移或正式部署完成。
