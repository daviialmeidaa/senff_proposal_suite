from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
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
