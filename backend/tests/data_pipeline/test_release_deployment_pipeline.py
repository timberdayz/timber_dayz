from pathlib import Path


def test_deploy_workflow_syncs_nginx_prod_conf():
    text = Path("scripts/build_deploy_bundle.sh").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert "nginx/nginx.prod.conf" in text


def test_deploy_workflow_creates_remote_directories_before_upload():
    text = Path(".github/workflows/deploy-production.yml").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert (
        "Failed to prepare remote deployment directory under ${PRODUCTION_PATH}"
        in text
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

    assert 'for file in config/*.yaml config/*.py; do' in text
    assert 'if [ "${base_name}" = "metabase_config.yaml" ]; then' in text
    assert 'copy_if_exists "${file}" "${BUNDLE_DIR}/config/${base_name}"' in text


def test_deploy_workflow_builds_and_uploads_single_deploy_bundle():
    text = Path(".github/workflows/deploy-production.yml").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert "deploy_bundle.tgz" in text
    assert 'BUNDLE_PATH="$(scripts/build_deploy_bundle.sh "$(pwd)" "temp/deploy_bundle.tgz")"' in text
    assert 'scp_with_retry "${BUNDLE_PATH}" ${PRODUCTION_PATH}/deploy_bundle.tgz' in text
    assert 'tar -xzf \\"${PRODUCTION_PATH}/deploy_bundle.tgz\\"' in text


def test_deploy_workflow_no_longer_scp_uploads_sql_and_nginx_files_individually():
    text = Path(".github/workflows/deploy-production.yml").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert 'for f in sql/init/*.sql; do' not in text
    assert 'scp_with_retry nginx/nginx.prod.conf ${PRODUCTION_PATH}/nginx/nginx.prod.conf' not in text
