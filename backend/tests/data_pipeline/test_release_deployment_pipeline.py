from pathlib import Path


def test_deploy_workflow_syncs_nginx_prod_conf():
    text = Path("scripts/build_deploy_bundle.sh").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert "nginx/nginx.prod.conf" in text
    assert "nginx/ssl/https.conf" in text


def test_deploy_workflow_creates_remote_directories_before_upload():
    text = Path(".github/workflows/deploy-production.yml").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert (
        "Failed to prepare remote deployment directory under ${PRODUCTION_PATH}" in text
    )
    for expected in (
        '\\"${PRODUCTION_PATH}\\"',
        '\\"${PRODUCTION_PATH}/config\\"',
        '\\"${PRODUCTION_PATH}/sql/init\\"',
        '\\"${PRODUCTION_PATH}/nginx\\"',
        '\\"${PRODUCTION_PATH}/nginx/ssl\\"',
    ):
        assert expected in text


def test_deploy_workflow_skips_legacy_metabase_uploads():
    text = Path(".github/workflows/deploy-production.yml").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert "docker-compose.metabase.yml (required for production)" not in text
    assert "scp_with_retry config/metabase_config.yaml" not in text


def test_remote_deploy_script_cleans_legacy_metabase_container():
    text = Path("scripts/deploy_remote_production.sh").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert "xihong_erp_metabase" in text
    assert (
        "docker stop xihong_erp_metabase" in text
        or "docker rm xihong_erp_metabase" in text
    )


def test_remote_deploy_script_removes_only_stopped_recreate_leftovers():
    """Phase 0.9 的残骸清理必须守住三条安全边界。

    背景
    ----
    docker compose v2 在 recreate 时把旧容器改名成 ``<12位哈希>_原名``。
    部署若在「改名 → 创建新容器」之间中断，残骸会留在磁盘上，
    **下一次部署必然在 Phase 1 撞上**
    ``Conflict. The container name ... is already in use``（v7.19.2 就是这样挂的）。
    因为哈希由容器配置决定、配置不变 ⇒ 哈希不变 ⇒ 不清理就会一直失败。

    边界
    ----
    1. 只处理**本项目** compose 留下的残骸（名字形如
       ``<12位哈希>_xihong_erp_<服务>``）⇒ 不会误伤别的项目；
    2. **只删已经停止的**（Exited / Created / Dead）⇒ 正在跑的容器一律不动，
       生产数据库不存在被误删的可能；
    3. 无论删不删都先打印现场 ⇒ 失败后可查。
    """
    text = Path("scripts/deploy_remote_production.sh").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert "Phase 0.9" in text
    # 名字必须限定本项目 + 哈希前缀 + 本项目服务名
    assert "[0-9a-f]{12}_xihong_erp_" in text
    # 只删已停止的容器
    assert "(Exited|Created|Dead|exited|created|dead)" in text
    # 正在运行的残骸只报告、不删除
    assert "left untouched on purpose" in text
    # 先打印现场
    assert "Leftover containers found" in text


def test_remote_deploy_script_does_not_load_metabase_compose_in_prod():
    text = Path("scripts/deploy_remote_production.sh").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert (
        'compose_cmd_base=("${compose_cmd_base[@]}" "-f" "docker-compose.metabase.yml")'
        not in text
    )
    assert "production no longer depends on Metabase" in text


def test_backend_dockerfile_includes_ops_dashboard_scripts():
    text = Path("Dockerfile.backend").read_text(encoding="utf-8", errors="replace")

    assert "check_postgresql_dashboard_ops.py" in text
    assert "migrate_cloud_sync_tables.py" in text
    assert "smoke_postgresql_dashboard_routes.py" in text
    assert "COPY sql/ops /app/sql/ops" in text
    assert "COPY sql/semantic /app/sql/semantic" in text
    assert "COPY sql/mart /app/sql/mart" in text
    assert "COPY sql/api_modules /app/sql/api_modules" in text
    assert "COPY scripts/init_metabase.py" not in text


def test_deploy_bundle_builder_skips_legacy_metabase_config():
    text = Path("scripts/build_deploy_bundle.sh").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert "for file in config/*.yaml config/*.py; do" in text
    assert 'if [ "${base_name}" = "metabase_config.yaml" ]; then' in text
    assert 'copy_if_exists "${file}" "${BUNDLE_DIR}/config/${base_name}"' in text


def test_deploy_workflow_builds_and_uploads_single_deploy_bundle():
    text = Path(".github/workflows/deploy-production.yml").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert "deploy_bundle.tgz" in text
    assert (
        'BUNDLE_PATH="$(scripts/build_deploy_bundle.sh "$(pwd)" "temp/deploy_bundle.tgz")"'
        in text
    )
    assert (
        'scp_with_retry "${BUNDLE_PATH}" ${PRODUCTION_PATH}/deploy_bundle.tgz' in text
    )
    assert 'tar -xzf \\"${PRODUCTION_PATH}/deploy_bundle.tgz\\"' in text


def test_deploy_workflow_no_longer_scp_uploads_sql_and_nginx_files_individually():
    text = Path(".github/workflows/deploy-production.yml").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert "for f in sql/init/*.sql; do" not in text
    assert (
        "scp_with_retry nginx/nginx.prod.conf ${PRODUCTION_PATH}/nginx/nginx.prod.conf"
        not in text
    )
    assert (
        "scp_with_retry nginx/ssl/https.conf ${PRODUCTION_PATH}/nginx/ssl/https.conf"
        not in text
    )


def test_deploy_workflow_sets_cnb_tag_on_a_real_command_line():
    text = Path(".github/workflows/deploy-production.yml").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert '\n          TAG="${GITHUB_REF#refs/tags/}"' in text
    assert (
        '# 鑾峰彇闀滃儚鏍囩锛堜粠 ref 涓彁鍙栵紝渚嬪 v4.22.4锛?          TAG="${GITHUB_REF#refs/tags/}"'
        not in text
    )


def test_deploy_workflow_frontend_metadata_keeps_v_prefixed_release_tag_rule():
    text = Path(".github/workflows/deploy-production.yml").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert "\n            type=semver,pattern=v{{version}}" in text


def test_remote_deploy_script_restores_requested_image_tag_after_loading_env():
    text = Path("scripts/deploy_remote_production.sh").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert 'REQUESTED_IMAGE_TAG="$(echo "${IMAGE_TAG}"' in text
    assert 'if [ "${IMAGE_TAG:-}" != "${REQUESTED_IMAGE_TAG}" ]; then' in text
    assert 'IMAGE_TAG="${REQUESTED_IMAGE_TAG}"' in text


def test_remote_deploy_initializes_cloud_sync_receiver_when_worker_enabled():
    text = Path("scripts/deploy_remote_production.sh").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert "ensure_cloud_sync_target_tables" in text
    assert "CLOUD_SYNC_WORKER_ENABLED" in text
    assert "migrate_cloud_sync_tables.py --target" in text
    assert (
        "# [FIX] 鍚屾椂鎺ㄩ€佸甫 v 鍓嶇紑鐨?tag锛坴4.20.5 / 4.20.5锛?            type=semver,pattern=v{{version}}"
        not in text
    )
