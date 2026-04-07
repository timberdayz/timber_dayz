import os


def _env(name: str, default: str) -> str:
    value = os.getenv(name, "").strip()
    return value or default


def admin_connection_kwargs() -> dict:
    return {
        "host": _env("TEST_DB_HOST", "127.0.0.1"),
        "port": int(_env("TEST_DB_PORT", "15432")),
        "user": _env("TEST_DB_USER", "erp_user"),
        "password": _env("TEST_DB_PASSWORD", "erp_pass_2025"),
        "dbname": _env("TEST_DB_ADMIN_DB", "postgres"),
    }


def database_connection_kwargs(dbname: str) -> dict:
    kwargs = admin_connection_kwargs()
    kwargs["dbname"] = dbname
    return kwargs


def database_url(dbname: str) -> str:
    host = _env("TEST_DB_HOST", "127.0.0.1")
    port = _env("TEST_DB_PORT", "15432")
    user = _env("TEST_DB_USER", "erp_user")
    password = _env("TEST_DB_PASSWORD", "erp_pass_2025")
    return f"postgresql://{user}:{password}@{host}:{port}/{dbname}"
