"""部署产物保留策略（磁盘有界化）的静态契约守护。

为什么要有这个文件
------------------
生产上 `/opt/xihong_erp` 有两处**只增不减**的堆积：

1. `backups/pre_deploy_*` —— 每次发版都会新建一个备份目录，实测已堆到 85 个；
2. `frontend_stale_*` —— 上一版前端源码树留在根目录，单个 313M。

它们都不是发版本身需要的东西，但会让服务器磁盘被慢慢吃满。
本文件把「哪些能删、哪些绝对不能删、删的时机」钉成静态断言，
让**误删**这类不可逆动作在合入前就被拦下来，而不是在生产上发生。

被守护的硬约束
--------------
1. 删除只发生在**成功发版之后**（`DEPLOYMENT_CUTOVER_COMPLETE=1` 之后），
   失败回滚路径上绝不删东西；
2. **只删目录**：`backups/` 下的独立 `.dump` 文件来源不明，可能留着手工排查的现场；
3. 本次发版刚创建的备份绝不能删（流水线在跑部署脚本之前也会建一个
   `pre_deploy_*`，它的时间戳比脚本启动略早）；
4. `PRODUCTION_PATH` 为空或 `/` 时拒绝执行；
5. 删除失败不能拖垮发版（每条删除都 `|| true`）；
6. logrotate 装不上时只 WARN 跳过，绝不让发版失败。
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SCRIPT = ROOT / "scripts" / "deploy_remote_production.sh"
BUNDLE_SCRIPT = ROOT / "scripts" / "build_deploy_bundle.sh"
LOGROTATE_CONF = ROOT / "nginx" / "logrotate-xihong.conf"


def _deploy_script() -> str:
    return DEPLOY_SCRIPT.read_text(encoding="utf-8")


def _bundle_script() -> str:
    return BUNDLE_SCRIPT.read_text(encoding="utf-8")


def _logrotate_conf() -> str:
    return LOGROTATE_CONF.read_text(encoding="utf-8")


def test_deploy_script_defines_both_retention_functions():
    """两个函数都必须存在 —— 少了任何一个，这条链路的意图就丢了。"""
    script = _deploy_script()

    assert "prune_deployment_artifacts() {" in script
    assert "install_logrotate_config() {" in script


def test_bundle_ships_the_logrotate_config_to_the_production_host():
    """logrotate 配置必须随包上生产机，否则脚本里那个源文件根本不存在。"""
    bundle = _bundle_script()

    assert "nginx/logrotate-xihong.conf" in bundle
    assert 'copy_if_exists "nginx/logrotate-xihong.conf"' in bundle


def test_logrotate_config_uses_copytruncate_and_bounded_retention():
    """轮转配置本身的四个要点。

    ``copytruncate`` 是必须的：nginx 进程在容器里并持有日志文件的句柄，
    宿主机上的 logrotate 拿不到容器内进程去做 ``nginx -s reopen``，
    只有 copytruncate 能保留 inode 与属主。

    ``create 0644`` 不写 owner/group：宿主机上文件属主与容器内 nginx 的 uid
    不一定一致，写死属主可能导致 nginx 之后写不进去。
    """
    conf = _logrotate_conf()

    assert "/opt/xihong_erp/logs/nginx" in conf
    assert "copytruncate" in conf
    assert "rotate 7" in conf
    assert "maxsize 100M" in conf
    assert "daily" in conf
    assert "missingok" in conf
    assert "notifempty" in conf
    assert "compress" in conf


def test_logrotate_install_skips_instead_of_failing_the_deployment():
    """logrotate 装不上时必须只 WARN 跳过 —— 轮转是收尾工作，不是发版前提。"""
    script = _deploy_script()

    assert "command -v logrotate" in script
    assert "[WARN] logrotate is not installed on this host" in script
    # 跳过路径必须以 return 0 收尾，而不是让脚本带着非 0 退出
    assert (
        "[WARN] ${source_config} is missing; nginx log rotation was NOT configured"
        in script
    )


def test_logrotate_install_validates_the_config_before_installing_it():
    """装之前必须先做语法校验。

    logrotate 的 ``-d``（debug）模式**退出码不足以判定成功**：实测当配置文件
    对 group/other 可写时，它会打印
    ``error: Ignoring <conf> because it is writable by group or others.``
    但退出码仍然是 0 ⇒ 必须同时检查输出里有没有被忽略 / 出错的痕迹，
    以及有没有真的 ``reading config file``。
    """
    script = _deploy_script()

    assert "logrotate_bin}" in script
    assert "-d --state" in script
    assert "reading config file" in script
    assert "Ignoring" in script


def test_retention_keeps_configured_number_of_backups():
    """保留数量必须可覆盖，且默认值写死成两个常量。"""
    script = _deploy_script()

    assert "KEEP_BACKUPS_COUNT:-3" in script
    assert "KEEP_OTHER_BACKUPS_COUNT:-1" in script


def test_retention_never_deletes_standalone_dump_files():
    """独立 .dump 文件一律不删。

    候选集用 ``find -type d`` 收集（文件天然不在其中），
    删除函数里还有一道 ``*.dump`` 显式保护 —— 双保险，
    防止以后有人把 ``-type d`` 去掉就误删现场。
    """
    script = _deploy_script()

    assert "*.dump)" in script
    assert "Keeping the standalone dump file" in script
    assert '-type d -name "${pattern}"' in script


def test_retention_only_removes_directories():
    """删除函数里必须有「是目录」的前置判断 —— 文件一律不删。"""
    script = _deploy_script()

    assert 'if [ ! -d "${target}" ]; then' in script


def test_retention_protects_the_backup_created_by_the_current_deployment():
    """本次发版刚创建的备份绝不能删。

    两条保护：脚本内 `perform_pre_migration_backup` 创建的那个（精确匹配），
    以及流水线在跑脚本之前创建的 `pre_deploy_*`（时间戳落在发版窗口 ±5 分钟内）。
    """
    script = _deploy_script()

    assert "CURRENT_DEPLOY_BACKUP_DIR" in script
    assert "is_current_deployment_backup" in script
    assert "DEPLOYMENT_STARTED_AT_EPOCH" in script
    assert "Keeping the backup created by this deployment" in script


def test_retention_refuses_to_run_without_a_safe_production_path():
    """PRODUCTION_PATH 为空或 / 时必须拒绝执行 —— 否则会对着根目录删东西。"""
    script = _deploy_script()

    assert "PRODUCTION_PATH is empty or '/'; artifact retention was skipped" in script


def test_retention_deletion_failures_never_fail_the_deployment():
    """每条删除都必须容错 —— 删除失败不能拖垮发版。"""
    script = _deploy_script()

    assert 'rm -rf -- "${target}" 2>/dev/null || true' in script
    assert "Could not remove ${target}; keeping it" in script


def test_retention_runs_only_after_a_successful_cutover():
    """保留策略必须排在 `DEPLOYMENT_CUTOVER_COMPLETE=1` 之后。

    失败回滚路径上删备份 = 把唯一的回滚资产删掉。
    """
    script = _deploy_script()

    cutover_index = script.index("DEPLOYMENT_CUTOVER_COMPLETE=1")
    prune_call_index = script.index("\nprune_deployment_artifacts\n")
    assert cutover_index < prune_call_index


def test_fallback_cron_is_idempotent_across_repeated_deploys():
    """兜底 cron 必须幂等 —— 重复发版不能越堆越多。

    踩过的坑：最初只用 grep 删掉两行标记行，标记块**里面**那条 cron 命令留了下来
    ⇒ 每发一次版就多一条重复任务（沙盒实测：三次发版后有三条 logrotate 任务）。
    修法是按块删（awk 跳过 begin..end 之间的所有行）。
    """
    script = _deploy_script()

    assert "inblock = 1" in script
    assert "inblock = 0" in script
    assert (
        "The fallback cron block looks incomplete; leaving the crontab untouched"
        in script
    )


def test_retention_reports_what_it_removed():
    """每次删除都要打印路径与占用，最后给一行汇总。"""
    script = _deploy_script()

    assert "Removing old backup: ${target}" in script
    assert (
        "Artifact retention applied: removed ${REMOVED_ARTIFACT_COUNT} items" in script
    )


# ---------------------------------------------------------------------------
# 用户级 cron 兜底 —— 生产上**实际会走**的那条路径
# ---------------------------------------------------------------------------
#
# 2026-11-10 生产实测：
#   * 流水线是以 ``deploy`` 用户跑的（uid=1002）；
#   * ``sudo`` **免密不可用**（``sudo -n true`` 失败）、``/etc/logrotate.d``
#     写不进去 ⇒ 主路径（装进系统目录）在这台机器上**必然失败**，
#     真正生效的是用户级 cron 兜底；
#   * 日志文件属主是 ``deploy:deploy`` 且可写 ⇒ 兜底里的 ``copytruncate`` 能成功；
#   * deploy 的 crontab 里已有 **acme.sh 证书续签**任务 —— 兜底一旦把它弄丢，
#     证书就会过期。
#
# ⇒ 这条路径会**改用户的 crontab**，必须被钉死。


def test_logrotate_falls_back_to_user_cron_when_system_dir_is_unusable():
    """系统目录写不进去时必须走用户级 cron 兜底，而不是就此放弃轮转。"""
    script = _deploy_script()

    assert "install_logrotate_user_cron() {" in script
    # 主路径失败后必须调用兜底
    assert "install_logrotate_user_cron" in script
    assert "user-level fallback" in script


def test_user_cron_fallback_never_drops_existing_crontab_entries():
    """兜底只许**追加**自己的块，绝不许弄丢用户原有条目（含 acme.sh 证书续签）。"""
    script = _deploy_script()

    # 幂等标记：重复发版不能堆出多条 cron
    assert "# >>> xihong nginx logrotate >>>" in script
    assert "# <<< xihong nginx logrotate <<<" in script
    # 写回前先备份
    assert "crontab -l > " in script
    # 失败必须还原
    assert "restoring the previous crontab" in script
    # 写回后逐条校验原有条目还在
    assert "would drop an existing crontab entry" in script
    # 新条目本身也要校验在位
    assert "the new entry is missing" in script
