from pathlib import Path


def test_nginx_prod_conf_no_longer_exposes_metabase_routes():
    text = Path("nginx/nginx.prod.conf").read_text(encoding="utf-8", errors="replace")

    assert "metabase:3000" not in text
    assert "location /app/" not in text
    assert 'location ^~ /metabase/' in text
    assert "return 404" in text


def test_prod_compose_no_longer_documents_metabase_as_runtime_dependency():
    text = Path("docker-compose.prod.yml").read_text(encoding="utf-8", errors="replace")

    assert "Nginx 依赖 Metabase" not in text
    assert "Metabase 服务在 docker-compose.metabase.yml 中定义" not in text
