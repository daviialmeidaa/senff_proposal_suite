from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values, load_dotenv, set_key


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"


@dataclass(frozen=True)
class EnvironmentConfig:
    key: str
    label: str
    auth_url: str
    api_url: str
    tenant_id: str
    username: str
    password: str
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str
    default_account: str
    default_store_code: str


def load_environment_file() -> None:
    if not ENV_FILE.exists():
        raise FileNotFoundError(f"Arquivo .env nao encontrado em {ENV_FILE}")

    load_dotenv(dotenv_path=ENV_FILE, override=False)


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Variavel obrigatoria nao definida no .env: {name}")
    return value


def get_environment_config(environment_key: str) -> EnvironmentConfig:
    prefix = environment_key.upper()

    return EnvironmentConfig(
        key=prefix,
        label=prefix.capitalize(),
        auth_url=_normalize_auth_url(_require_env(f"{prefix}_AUTH_URL")),
        api_url=_normalize_api_url(_require_env(f"{prefix}_API_URL")),
        tenant_id=_require_env(f"{prefix}_TENANT_ID"),
        username=_require_env(f"{prefix}_USER"),
        password=_require_env(f"{prefix}_PASS"),
        db_host=_require_env(f"{prefix}_DB_HOST"),
        db_port=int(_require_env(f"{prefix}_DB_PORT")),
        db_name=_require_env(f"{prefix}_DB_DATABASE"),
        db_user=_require_env(f"{prefix}_DB_USERNAME"),
        db_password=_require_env(f"{prefix}_DB_PASSWORD"),
        default_account=_require_env("DEFAULT_ACCOUNT"),
        default_store_code=_require_env("DEFAULT_STORE_CODE"),
    )



def write_local_config(
    db_database: str,
    db_host: str,
    db_password: str,
    db_username: str,
    db_port: str,
    auth_url: str,
    api_url: str,
    tenant_id: str,
    user: str,
    password: str,
) -> None:
    mapping = {
        "LOCAL_DB_DATABASE": db_database,
        "LOCAL_DB_HOST": db_host,
        "LOCAL_DB_PASSWORD": db_password,
        "LOCAL_DB_USERNAME": db_username,
        "LOCAL_DB_PORT": db_port,
        "LOCAL_AUTH_URL": auth_url,
        "LOCAL_API_URL": api_url,
        "LOCAL_TENANT_ID": tenant_id,
        "LOCAL_USER": user,
        "LOCAL_PASS": password,
    }
    for key, value in mapping.items():
        set_key(str(ENV_FILE), key, value)
    load_dotenv(dotenv_path=ENV_FILE, override=True)


def read_local_config() -> dict[str, str]:
    """Reads LOCAL_* variables directly from .env file (bypasses os.environ cache)."""
    values = dotenv_values(dotenv_path=ENV_FILE)
    return {
        "db_host": values.get("LOCAL_DB_HOST") or "",
        "db_port": values.get("LOCAL_DB_PORT") or "",
        "db_database": values.get("LOCAL_DB_DATABASE") or "",
        "db_username": values.get("LOCAL_DB_USERNAME") or "",
        "db_password": values.get("LOCAL_DB_PASSWORD") or "",
        "auth_url": values.get("LOCAL_AUTH_URL") or "",
        "api_url": values.get("LOCAL_API_URL") or "",
        "tenant_id": values.get("LOCAL_TENANT_ID") or "",
        "user": values.get("LOCAL_USER") or "",
        "password": values.get("LOCAL_PASS") or "",
    }


def _normalize_auth_url(auth_url: str) -> str:
    auth_url = auth_url.rstrip("/")
    if auth_url.endswith("/auth/v1/auth"):
        return auth_url
    if auth_url.endswith("/auth"):
        return f"{auth_url}/v1/auth"
    return auth_url



def _normalize_api_url(api_url: str) -> str:
    api_url = api_url.rstrip("/")
    if api_url.endswith("/api/v1"):
        return api_url
    if api_url.endswith("/api"):
        return f"{api_url}/v1"
    return api_url
