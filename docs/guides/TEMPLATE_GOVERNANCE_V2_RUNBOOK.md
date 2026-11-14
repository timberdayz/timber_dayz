# 模板治理闭环 v2 发布与回退 Runbook（v7.29.0）

> 适用版本：**v7.29.0**（发布 tag）
> 发布日期：2026-11-14
> 设计依据：`docs/superpowers/specs/2026-11-14-template-governance-v2-design.md`
> 发布流程真源：`docs/guides/RELEASE_CHECKLIST.md`
> SSH 通道真源：`docs/guides/SSH_ACCESS.md`

---

## 1. 这次发布是什么

一次**事故收口**发布：把 2026-11-13（v7.26.0）引入的漂移判定口径错误拉回
2026-11-07 业务规格，并修掉与之叠加的三处闭环 bug。

| 批次 | 内容 | 性质 |
|---|---|---|
| 0 | 仓库 `.ps1` 清除硬编码数据库密码 + 纯 ASCII 化 | **安全修复** |
| 1 | 发布即重检静默漏检、`recheck` 字段被 Pydantic 丢弃、文件级结论写错行 | **纯 bug 修复** |
| 2 | 漂移口径回退到「核心字段 = 需求」（多一列不再阻断） | **业务口径变更**（唯一一处） |
| 3 | 模板决策资产进 Git（27 份定义 + 投影 + 差异守卫 + CI） | **新增能力** |
| 4 | 契约语义拆分（登记事实不可变）+ 发布闭环指标 | **新增能力** |

**本次没有任何数据库结构变更**（`template_contract_current` 是 JSONB 内的键，不是新列），
因此**不需要数据迁移**，回退也不涉及数据库回滚。

---

## 2. 上线前检查（全部已在本地/生产只读确认）

| # | 检查 | 命令 | 期望 | 状态 |
|---|---|---|---|---|
| 1 | 宽回归 | `python -m pytest backend/tests -k "template or drift or semantic_contract or core_field or hash or contract or governance or ingest" -q` | 0 failed | ✅ 1688+ passed |
| 2 | 静态门禁 | `python -m ruff check <改动文件>` / `python -m black --check <改动文件>` | 全过 | ✅ |
| 3 | 前端 | `cd frontend && npx vue-tsc --noEmit && npx vite build` | exit 0 | ✅ |
| 4 | 定义资产离线校验 | `python scripts/apply_template_definitions.py --validate-only` | OK | ✅ |
| 5 | 定义 ↔ 库内一致 | `python scripts/apply_template_definitions.py --check` | 27/27 一致，退出码 0 | ✅ |
| 6 | 口径影响面 | `python scripts/replay_drift_caliber.py` | 497 文件结论零变化 | ✅ |
| 7 | 生产基线健康 | `ssh deploy@… "docker ps --format '{{.Names}}\|{{.Status}}'"` | 全 healthy | ✅ v7.28.0 |

> 检查 6 的结论只说明**存量**不受影响；新行为对**新文件**生效，
> 这正是本次要修的东西（见 §5 第 2 条验证）。

---

## 3. 部署

部署由 **push tag** 触发（不是 `origin/main`）：

```powershell
# 3.1 先把 main 推到两个镜像（GitHub SSH-443 + CNB HTTPS），fail-closed
powershell -ExecutionPolicy Bypass -File .\scripts\sync_main_mirrors.ps1 -Sync

# 3.2 打 tag 并推到 GitHub（这一步触发生产部署）
git tag -a v7.29.0 -m "..."
git push origin v7.29.0

# 3.3 再把**同一个 tag 对象**推到 CNB（CNB Git 只是代码镜像，推 tag 是 inert 的）
git push cnb refs/tags/v7.29.0:refs/tags/v7.29.0

# 3.4 验证两个镜像上的 tag 是同一个对象
git ls-remote --tags cnb refs/tags/v7.29.0
git ls-remote --tags "ssh://git@ssh.github.com:443/timberdayz/timber_dayz.git" refs/tags/v7.29.0
```

⚠️ **绝不回填 tag 到 GitHub**——那会触发第二次部署。
⚠️ tag 必须在两个镜像上都是**同一个 tag 对象**，不要重新创建。

### 部署脚本会自动做什么

`scripts/deploy_remote_production.sh` 的 Phase 3 会执行：

```bash
docker compose ... up -d --no-build --no-deps backend-api celery-worker celery-beat
```

⇒ **celery-worker / celery-beat 会自动用新镜像重建**，不需要人工重启容器。
（本次发布前生产已是 v7.28.0 且 worker/beat `restarts=0, oom=false`，属健康基线。）

---

## 4. 上线后验证（**必须逐条人工确认，不接受「流水线绿」代替**）

### 4.1 容器与镜像

```powershell
ssh -i "$env:USERPROFILE\.ssh\github_actions_deploy" deploy@134.175.222.171 `
  "docker ps --format '{{.Names}}|{{.Status}}|{{.Image}}' | grep -E 'celery|backend_api|frontend'"
```

期望：四个容器都 `Up ... (healthy)`，镜像 tag = `v7.29.0`。

### 4.2 决策资产一致性

```powershell
python scripts/apply_template_definitions.py --check
```

期望：`完全一致: 27`，退出码 **0**。
（若非 0，说明生产库与仓库定义已漂移 —— 查清后再决定是否 `--apply` 投影。）

> ⚠️ **这条在 v7.29.0 上跑不了**：镜像里既没有 `templates/` 也没有
> `scripts/apply_template_definitions.py`（`Dockerfile.backend` 用白名单式 COPY，
> 新脚本没登记 ⇒ 静默缺席）。已在 **v7.29.1** 补齐，见 §4.5。

### 4.3 闭环真 bug（本次事故的正面战场，**必须人工点一次**）

1. 造一个**多一列**的文件（平台导出比模板多一列）放入采集目录；
2. 在治理面板上对该维度**保存模板**；
3. **立刻**（不等待 15 分钟巡检）看面板：应出现三态之一
   （用户待办 / 系统待办 / 已放行），**不应**再显示「仍有字段对不上」；
4. 生产日志应出现：

```powershell
ssh -i "$env:USERPROFILE\.ssh\github_actions_deploy" deploy@134.175.222.171 `
  "docker logs xihong_erp_celery_worker --tail 200 | grep -i 'TemplateRecheck'"
```

期望：出现 `[TemplateRecheck] 维度重检完成 ... checked=N`（N > 0）。

### 4.4 闭环指标

```powershell
python scripts/template_release_sla_metric.py --window-minutes 15
```

期望：出现**至少一个**发布事件有重估记录，且比例非空。
若仍显示「无数据」，说明 §4.3 没真正触发重检（埋点没写进去）——**这本身是故障信号**。

### 4.5 v7.29.1 补丁与本次实测结果（2026-11-14）

#### 4.5.1 v7.29.1 为什么存在

v7.29.0 上线后逐条核查 §4.1–§4.4 时发现：`Dockerfile.backend` 对 `scripts/` 用的是
**白名单式 COPY**，v7.29.0 新增的 5 个脚本与 `templates/` 目录**全都没登记**
⇒ 生产镜像里 `ls /app/templates` 返回 `No such file or directory`。

- **业务不受影响**（判定逻辑都在 `backend/` 里）；
- 但 §4.2 的差异守卫与 §4.4 的闭环指标**在生产根本跑不起来**。

⇒ v7.29.1 只改 `Dockerfile.backend`（补 `COPY templates /app/templates` + 5 个脚本），
**无业务代码、无数据库变更、无迁移**；并新增 2 条守护测试把这条变成流水线里会红的事实。

#### 4.5.2 实测结果

**生产（只读，241 个 catalog 文件）**

| 项 | 结果 |
|---|---|
| `status='template_update_required'` 的文件 | **0** |
| `template_status` 分布 | `file_missing` 231（原始文件已被清理，存量）/ `ready` 9 / `alias_only` 1 |
| 多列文件被阻断数 | **0** |
| 少列文件被阻断数 | **0** |
| 判定口径 | `drift_caliber=current`，`legacy_caliber_enabled=False` |
| 镜像内新代码 | `DRIFT_CALIBER_ENV` ×2、`legacy_caliber_enabled` ×3、`normalize_dimension_placeholder` ×2、`last_recheck_template_id` ×1、`template_contract_current` ×3 |

> `file_missing` 是**存量**：原始文件早被清理、`catalog_files` 行还在。
> 该状态**不阻断**，与本次发布无关。

**口径 A/B 对照（同一文件、同一次判定）**

| 口径 | `template_status` | `governance_status` | 阻断 | 结论 |
|---|---|---|---|---|
| `current`（v7.29.0 起） | `alias_only` | `non_breaking_drift` | **否** | 「只多了 1 列, 不影响入库」 |
| `legacy`（回退开关） | `update_required` | `breaking_drift` | **是** | 「新增1个字段, 删除0个字段 (匹配率: 99.2%)」 |

⇒ 这就是事故的正面战场：**旧口径下 TikTok 文件多一列就被判「需要更新模板」**，
运营改完模板仍看到「仍有字段对不上」。

**端到端（真实 HTTP `POST /api/field-mapping/templates/save`）**

```text
HTTP 200
response.data.recheck = {"checked": 1, "released": 1, "still_blocked": 0, "file_ids": [3061]}
文件行：status = pending（由 template_update_required 放行）
        auto_ingest.last_recheck_at = 2026-11-14T10:28:49Z
        auto_ingest.last_recheck_template_id = 382
        auto_ingest.last_status = readiness_recovered
日志：  [TemplateRecheck] 维度重检完成 platform=tiktok domain=orders granularity=monthly: checked=1 released=1 still_blocked=0
```

⇒ 面板三态命中第 1 态「模板已更新，N 个文件已通过治理复核并放行入库」；
`recheck` 字段**确实出现在响应里**（历史事故根因：`TemplateSaveData` 未声明该字段 ⇒
Pydantic 静默丢弃 ⇒ 前端 `result.data.recheck` 恒为 `undefined` ⇒ 只能「按列表猜」）。

#### 4.5.3 定义基线取错了库（v7.29.2 修正）

v7.29.1 把守卫装进生产镜像后，第一次跑 `--check` 就报 **6 个维度不一致**：

```text
仓库定义 27 / 库内 published 27 / 完全一致 21 / 存在差异 6
```

⇒ **不是守卫坏了，是基线取错了。** 批次 3 的定义是从**本机开发库**导出的，
而开发库带诊断产物（`tiktok/orders/monthly` 的 186 列版本）、版本也和生产不同步。

最危险的一条：仓库基线 186 列、生产真实文件只有 184 列 ⇒
**照着仓库基线投影反而会把生产改错**。

⇒ v7.29.2 在生产容器内**只读**导出（`export_template_definitions.py --out /tmp/...`），
取回 27 份替换仓库里对不上的 6 份。上线后生产 `--check` ⇒ **完全一致 27 / 差异 0 / 退出码 0**。

> ⚠️ **本机开发库与仓库定义会继续不一致**（开发库 ≠ 生产库，本来就如此）。
> 不要拿开发库的 `--check` 结果当生产结论。
>
> ⚠️ 待业务确认：`miaoshou/inventory/snapshot` 的生产模板**没有核心字段清单**
> ⇒ 按 B1 口径该维度少列会阻断。需要业务先定「这个维度要哪些数据」，
> 再用 `--apply` 投影。**运维不替业务做这个决定。**

---

## 5. 回退方案

### 5.1 先分诊：是哪一层出问题？

| 现象 | 回退手段 | 生效方式 | 数据影响 |
|---|---|---|---|
| 面板/入库判定**不对**（多列仍被拦、或核心字段缺失没被拦） | **口径开关**（见 5.2） | 改环境变量 + 重启容器 | 无 |
| 重检不生效 / 面板显示不对 | revert 提交 + 重新部署 | 走发版流程 | 无 |
| 容器起不来 / 部署失败 | 部署脚本自带回滚（回到上一个 tag 的镜像） | 重新触发上一个 tag 的部署 | 无 |
| 入库数据错了 | **不要回退** —— 先只读核查，再单独处置 | — | 需人工判断 |

### 5.2 口径开关（最快的回退手段，无需改代码/重新构建镜像）

本次**唯一的业务口径变更**（多一列是否阻断）挂了一个运行时开关：

```bash
# 生产上临时切回旧口径
# 编辑 ${PRODUCTION_PATH}/.env.cleaned, 加一行:
TEMPLATE_DRIFT_CALIBER=legacy

# 然后重启后端三件套让环境变量生效
docker compose ... up -d --no-build --no-deps backend-api celery-worker celery-beat
```

回退后：`多一列 ⇒ 阻断`（2026-11-13 的旧行为），其余规则完全不变。

切回新口径：删掉该行（或设为 `current`），再重启一次。

> ⚠️ 开关**只**影响「多一列」这一条规则。核心字段缺失阻断、值形态漂移阻断、
> 清单未配置阻断在两套口径下**完全一致**。
> 守护测试：`backend/tests/data_pipeline/test_drift_classification_ssot.py`
> （`test_legacy_caliber_switch_reintroduces_added_column_blocking` 等 3 条）。

### 5.3 代码回退（口径开关不足以覆盖时）

```powershell
# 找到本次的提交
git log --oneline -10

# 回退指定提交（本次涉及的代码提交见设计文档 §7.1）
git revert <commit-sha>

# 重新走发布流程（tag 驱动）
powershell -ExecutionPolicy Bypass -File .\scripts\sync_main_mirrors.ps1 -Sync
git tag -a v7.29.1 -m "revert: ..."
git push origin v7.29.1
```

### 5.4 回退触发条件（满足任一即回退）

1. 入库数据出现**错值**（不只是延迟）—— 立即回退并只读核查；
2. `apply_template_definitions.py --check` 持续非 0 且无法解释；
3. worker/beat 出现 crash loop（`restarts` 持续增长）；
4. 面板判定与实际入库行为不一致（§4.3 验证不通过）。

---

## 6. 本次已知的副作用

| # | 事项 | 说明 |
|---|---|---|
| 1 | **凭据应视为已泄露** | 那个数据库密码曾在公开仓库里。**本次发布后应尽快轮换**，并同步更新生产 `.env.cleaned` 与采集机配置 |
| 2 | 模板版本号跳号 v9–v12 | `tiktok/orders/monthly` 的内容与 v8 完全一致，是诊断动作产生的。版本号仍是运行时状态，**本次未根治** |
| 3 | 闭环指标首日可能仍显示「无数据」 | 埋点本次才加；存量文件没有记录。**下一次真实模板变更**后才有数 |
| 4 | `--apply` 写库路径未在真实库实测 | 为避免又一次版本跳号，本次只用 `--check` 验证；写库路径可在允许跳号时试一次 |
| 5 | 仓库形态 `.ps1` 仅 `sync_templates_to_cloud.ps1` 达成纯 ASCII | 其余含中文的 `.ps1` 在 GBK 代码页下**恰好**解析通过，属运气好（V2 债） |

---

## 7. 交接

- 本次发布的完整改动清单、验证证据、影响面结论：
  `docs/superpowers/specs/2026-11-14-template-governance-v2-design.md` §7
- 模板决策资产的使用方式：`templates/README.md`
- 发布流程真源：`docs/guides/RELEASE_CHECKLIST.md`
