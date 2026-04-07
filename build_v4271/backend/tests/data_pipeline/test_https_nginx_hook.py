from pathlib import Path


def test_nginx_prod_conf_includes_optional_ssl_fragments():
    text = Path("nginx/nginx.prod.conf").read_text(encoding="utf-8", errors="replace")

    assert "include /etc/nginx/ssl/*.conf;" in text
