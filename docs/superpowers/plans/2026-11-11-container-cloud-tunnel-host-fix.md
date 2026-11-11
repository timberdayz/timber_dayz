# 容器侧云端隧道地址修正（2026-11-11）

- 关联版本：v7.21.0 上线后的**部署后实测**发现
- 关联方案：`docs/superpowers/plans/2026-11-11-shop-identity-guard-activation.md`（守护落地）
- 主题：让**采集机侧**的「云端同步链路完整性巡检」真的连得上云端

## 现象（部署后实测，不是推理）

v7.21.0 部署完成后，采集机本地库 `ops.pipeline_run_log` 出现一条：

| 字段 | 值 |
|---|---|
| `pipeline_name` | `cloud_sync_integrity_check_unreachable` |
| `status` | `failed` |
| `started_at` | 2026-11-11 04:37:00Z（= 12:37 CST，采集机本地整点后 37 分） |
| `error_message` | `ConnectionRefusedError: [Errno 111] Connect call failed ('127.0.0.1', 15433)` |

同一时刻隧道看门狗报 `[OK] tunnel is up: 127.0.0.1:15433`（12:37:03），
`ssh` 进程自 11:34:48 起一直是同一个（没断过）⇒ **不是隧道掉了**。

## 根因：一个变量名，两个语义相反的运行环境

| 运行环境 | 隧道在哪 | 该填什么 | 填错的后果 |
|---|---|---|---|
| **宿主进程**（`start_collection_formal.ps1` 拉起的后端 / 云端同步 worker） | 本机 | `127.0.0.1` | 填 `host.docker.internal` 在宿主上没有意义 ⇒ 反而连不上 |
| **容器内**（`celery-worker` / `celery-beat` / `backend-collector`） | Docker 宿主 | `host.docker.internal` | 填 `127.0.0.1` ⇒ 连到**容器自己** ⇒ 必然 `ECONNREFUSED` |

`CLOUD_SYNC_TUNNEL_HOST` 这**一个**变量名被两边共用，而 compose 变量插值
**优先取进程环境变量**；采集机启动脚本会把 `.env.collection.local`
（里面正是 `CLOUD_SYNC_TUNNEL_HOST=127.0.0.1`，对宿主进程是**对的**）
导入进程环境 ⇒ 容器最终拿到 `127.0.0.1`。

容器内实测（`docker exec` 直连）：

```
host.docker.internal:15433 -> 0   (connect_ex = 0，通)
127.0.0.1:15433           -> 111  (connect_ex = ECONNREFUSED，拒)
```

⇒ 隧道是好的，**地址填错了**。

## 为什么这比「连不上」更严重

`CLOUD_SYNC_TUNNEL_ENABLED=true` 时，容器里的巡检**恒定**报「云端不可达」，
每小时一次 ⇒ **假警报把真信号淹掉**。

这恰好违反本次改造的初衷：守卫的价值在于「云端真停更时有人知道」；
如果它每小时都在喊「云端不可达」，真警报当场作废 —— 与 2026-11-07 事故里
「三个信号同时存在却没人看见」是同一类失败。

## 修法

容器侧的 `CLOUD_SYNC_TUNNEL_HOST` **钉死为字面量** `host.docker.internal`，
不再插值：

```yaml
CLOUD_SYNC_TUNNEL_HOST: host.docker.internal
```

理由：

1. 容器里隧道宿主**恒为** `host.docker.internal`（隧道永远在 Docker 宿主上）；
2. 插值会被宿主进程的同名环境变量改回 `127.0.0.1` ⇒ 必须**断掉插值这条路**；
3. 宿主侧不受影响 —— `normalize_cloud_database_url` 在「非容器内」时
   直接原样保留主机名，根本不看 `CLOUD_SYNC_TUNNEL_HOST`。

宿主进程那侧仍然保留 `CLOUD_SYNC_TUNNEL_HOST=127.0.0.1`（`env.collection.local`），
并在示例文件里写明它是**宿主语义**，不能抄进容器。

### 生产为什么不受影响

生产上「云端」就是自己：`CLOUD_DATABASE_URL` 的主机名是 `postgres`
（容器网络地址，**非回环**）⇒ 代码走 `not_loopback_host` 分支，**不改写**主机名；
生产 compose 的 `CLOUD_SYNC_TUNNEL_ENABLED` 默认 `false`。本次改动**不动生产 compose**。

## 交付物

| 文件 | 作用 |
|---|---|
| `docker-compose.dev.yml`（celery-worker / celery-beat） | 容器侧隧道宿主钉死为字面量 |
| `docker-compose.collection-cloud-sync.yml`（backend-collector） | 同上 |
| `env.collection.local.example` | 写明 `CLOUD_SYNC_TUNNEL_HOST=127.0.0.1` 是**宿主语义**，容器侧由 compose 钉死 |
| `tests/test_container_cloud_tunnel_host_contract.py` | 10 条契约守护（容器侧必须是字面量且非插值 / 隧道默认开 / worker 与 beat 一致 / 生产不受影响 / 示例文件宿主语义） |

## 验证

| 项 | 结果 |
|---|---|
| 新增契约测试 | `tests/test_container_cloud_tunnel_host_contract.py` 全过 |
| 关联既有守护 | `tests/test_shop_identity_compose_env_contract.py`、`backend/tests/test_collection_cloud_database_url.py` 全过（43 条） |
| 容器内实测（修复前） | `host.docker.internal:15433` 通、`127.0.0.1:15433` 拒 ⇒ 根因确认 |
| 容器内实测（修复后） | 重建容器后巡检不再报 `unreachable`（见下节实测记录） |
| 生产 | 未改动生产 compose；生产巡检在 v7.21.0 上已实跑成功（副本 `ok`、`degraded_semantic_months=0`） |

## 遗留

- 采集机侧 My / PH 店铺的登录组件在无人值守下失败（`登录组件执行失败`），
  需要人工在有头浏览器里重新登录一次；这是**账号态**问题，与本次改动无关，
  但会让对应店铺的云端链继续陈旧。
