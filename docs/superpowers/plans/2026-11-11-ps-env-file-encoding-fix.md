# PowerShell env 文件读取的编码修正（2026-11-11）

- 关联版本：v7.21.0 上线后的**部署后实测**发现
- 关联方案：`docs/superpowers/plans/2026-11-11-container-cloud-tunnel-host-fix.md`（容器侧隧道地址）
- 主题：让 PowerShell **真的把 env 文件读完**

## 现象

在采集机上重建 celery 容器时，容器环境出现了**反直觉**的结果：

| 变量 | 期望 | 实际 |
|---|---|---|
| `CLOUD_SYNC_TUNNEL_HOST` | `host.docker.internal` | ✅ 对 |
| `SHOP_IDENTITY_ALIGNMENT_EFFECTIVE_DATE` | `2026-12-01` | ❌ **空** |
| `SHOP_IDENTITY_SEMANTIC_UNKNOWN_RATE_THRESHOLD` | `0` | ❌ **空** |
| `SHOP_IDENTITY_CONFLICT_NOTIFY_ENABLED` | `1` | ❌ **空** |

但这三个变量**明明白白写在** `.env.collection.local` 里。

## 根因：PS 5.1 按 ANSI(GBK) 解码无 BOM 文件

`scripts/start_collection_formal.ps1` 与 `scripts/watch_cloud_sync_tunnel.ps1` 里的
`Import-EnvFile` 用的是 `Get-Content $Path` —— **没指定编码**。

Windows PowerShell 5.1 读**无 BOM** 文件时，默认用**系统 ANSI 代码页**
（中文机器上是 GBK）。而 `.env.collection.local` 里**有中文注释块**：

```
33: [# 店铺身份「保未来」三件套（2026-11-11 落地）]
34: [# 生效日 = 2026-12-01：云端 2026-11 的 unknown 占比高达 56.69%（那是事故现场）。]
35: [# 若配成 2026-11-12，11 月整月会进「新问题」档 => 巡检每小时都红 => 告警当场作废。]
36: [SHOP_IDENTITY_ALIGNMENT_EFFECTIVE_DATE=2026-12-01]
```

GBK 解码把中文行解坏 ⇒ 解析中断 ⇒ **中文注释之后的每一个变量都被静默丢弃**。

实测（同一台机器、同一份文件、同一段解析代码，只差编码）：

| 读法 | 导入到的变量数 | `SHOP_IDENTITY_*` |
|---|---|---|
| `Get-Content $Path`（默认 ANSI/GBK） | 12 | **三个全丢** |
| `Get-Content -LiteralPath $Path -Encoding UTF8` | 全部 | `2026-12-01` / `0` / `1` |

⇒ **中间没有任何报错**：变量只是不见了。

## 为什么后果比「少配一个开关」严重

采集机的 compose 插值**优先取进程环境变量** ⇒ 变量没进进程环境 ⇒
容器拿到的就是空值 ⇒ **看起来配了、其实没生效**。

这与仓库规则「环境变量配在 `.env` 里 ≠ 容器里读得到」是同一个陷阱的另一半：
不是 compose 没声明，而是**值根本没传进去**，而且**没有任何声音**。

## 修法

两处 `Import-EnvFile` 都改成显式编码：

```powershell
Get-Content -LiteralPath $Path -Encoding UTF8 | ForEach-Object { ... }
```

* `-Encoding UTF8` —— 这些 `.env` 就是无 BOM 的 UTF-8；
* `-LiteralPath` —— 路径含 `[` / `]` 时 `-Path` 会被当成通配符。

## 交付物

| 文件 | 作用 |
|---|---|
| `scripts/start_collection_formal.ps1` | `Import-EnvFile` 显式 UTF-8 |
| `scripts/watch_cloud_sync_tunnel.ps1` | 同上（两处本来就「kept in sync」） |
| `tests/test_ps_env_file_encoding_contract.py` | 12 条契约守护（必须显式 UTF8 / 必须 `-LiteralPath` / 必须无 BOM UTF-8 / 两处写法必须同步） |

## 验证

| 项 | 结果 |
|---|---|
| 新增契约测试 | 12 条全过 |
| 关联既有守护 | `tests/test_cloud_sync_tunnel_watchdog.py`、`backend/tests/test_collection_startup_scripts.py` 全过（合计 21 条） |
| 本机实测 | 不带 `-Encoding` 丢 3 个变量；带 `-Encoding UTF8` 全部导入（同一份 `.env.collection.local`） |
| 容器环境重建后 diff | **仅** `CLOUD_SYNC_TUNNEL_HOST` 一项变化，三件套恢复为 `2026-12-01` / `0` / `1` |

## 遗留

- 采集机侧的店铺账号有部分登录失败（平台侧拦截，需人工重新登录），
  属账号态问题，与本次改动无关；
- `env.*.example` 里若以后加入中文注释，同样必须保证读它们的脚本显式 UTF-8。
