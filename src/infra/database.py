from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from functools import lru_cache
from threading import Lock

import psycopg2
from psycopg2.extensions import connection as PsycopgConnection
from psycopg2.pool import ThreadedConnectionPool

from src.core.config import EnvironmentConfig


_POOL_LOCK = Lock()
_DB_POOLS: dict[tuple[str, int, str, str], ThreadedConnectionPool] = {}


@dataclass(frozen=True)
class Agreement:
    id: str
    name: str


@dataclass(frozen=True)
class Product:
    id: str
    name: str


@dataclass(frozen=True)
class SaleModality:
    id: str
    name: str


@dataclass(frozen=True)
class WithdrawType:
    id: str
    name: str


@dataclass(frozen=True)
class SerproAgencyOption:
    agency_id: str
    agency_code: str
    agency_name: str
    sub_id: str
    sub_code: str
    sub_name: str
    upag_id: str
    upag_code: str
    upag_name: str


def connect(config: EnvironmentConfig) -> PsycopgConnection:
    return psycopg2.connect(
        host=config.db_host,
        port=config.db_port,
        dbname=config.db_name,
        user=config.db_user,
        password=config.db_password,
        connect_timeout=10,
    )


@contextmanager
def pooled_connection(config: EnvironmentConfig):
    pool = _get_pool(config)
    connection = pool.getconn()
    connection.autocommit = True
    try:
        yield connection
    finally:
        pool.putconn(connection)


def _get_pool(config: EnvironmentConfig) -> ThreadedConnectionPool:
    pool_key = (config.db_host, config.db_port, config.db_name, config.db_user)
    with _POOL_LOCK:
        pool = _DB_POOLS.get(pool_key)
        if pool is not None:
            return pool

        pool = ThreadedConnectionPool(
            minconn=1,
            maxconn=6,
            host=config.db_host,
            port=config.db_port,
            dbname=config.db_name,
            user=config.db_user,
            password=config.db_password,
            connect_timeout=10,
        )
        _DB_POOLS[pool_key] = pool
        return pool


def test_connection(config: EnvironmentConfig) -> None:
    with pooled_connection(config) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1;")
            cursor.fetchone()


def fetch_agreements(config: EnvironmentConfig) -> list[Agreement]:
    return list(_fetch_agreements_cached(config))


@lru_cache(maxsize=8)
def _fetch_agreements_cached(config: EnvironmentConfig) -> tuple[Agreement, ...]:
    query = """
        SELECT id, name
        FROM agreements
        WHERE name IS NOT NULL
        ORDER BY id ASC;
    """

    with pooled_connection(config) as conn:
        with conn.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()

    return tuple(Agreement(id=str(row[0]), name=row[1]) for row in rows)


def fetch_products(config: EnvironmentConfig) -> list[Product]:
    return list(_fetch_products_cached(config))


@lru_cache(maxsize=8)
def _fetch_products_cached(config: EnvironmentConfig) -> tuple[Product, ...]:
    query = """
        SELECT id, name
        FROM products
        WHERE name IS NOT NULL
        ORDER BY id ASC;
    """

    with pooled_connection(config) as conn:
        with conn.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()

    return tuple(Product(id=str(row[0]), name=row[1]) for row in rows)


def fetch_sale_modalities(config: EnvironmentConfig) -> list[SaleModality]:
    return list(_fetch_sale_modalities_cached(config))


@lru_cache(maxsize=8)
def _fetch_sale_modalities_cached(config: EnvironmentConfig) -> tuple[SaleModality, ...]:
    query = """
        SELECT id, name
        FROM sale_modalities
        WHERE name IS NOT NULL
        ORDER BY id ASC;
    """

    with pooled_connection(config) as conn:
        with conn.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()

    return tuple(SaleModality(id=str(row[0]), name=row[1]) for row in rows)


def fetch_withdraw_types(config: EnvironmentConfig) -> list[WithdrawType]:
    return list(_fetch_withdraw_types_cached(config))


@lru_cache(maxsize=8)
def _fetch_withdraw_types_cached(config: EnvironmentConfig) -> tuple[WithdrawType, ...]:
    query = """
        SELECT id, name
        FROM withdraw_types
        WHERE name IS NOT NULL
        ORDER BY id ASC;
    """

    with pooled_connection(config) as conn:
        with conn.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()

    return tuple(WithdrawType(id=str(row[0]), name=row[1]) for row in rows)


def check_unico_id_ready(config: EnvironmentConfig, proposal_id: str | int) -> bool:
    query = """
        SELECT unico_id_cloud_process_id
        FROM unico_id_cloud_process_proposals
        WHERE proposal_id = %s
        LIMIT 1;
    """
    with pooled_connection(config) as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, (str(proposal_id),))
            row = cursor.fetchone()
    if row is None:
        return False
    value = row[0]
    return value is not None and str(value).strip() != ""


def check_ccb_exists(config: EnvironmentConfig, contract_code: str) -> bool:
    query = """
        SELECT 1
        FROM ccbs
        WHERE code = %s
        LIMIT 1;
    """
    with pooled_connection(config) as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, (contract_code,))
            return cursor.fetchone() is not None


def fetch_serpro_agency_options(
    config: EnvironmentConfig,
    orgao_code: str,
) -> list[SerproAgencyOption]:
    normalized_code = orgao_code.strip()
    if not normalized_code:
        return []

    return list(_fetch_serpro_agency_options_cached(config, normalized_code))


@lru_cache(maxsize=64)
def _fetch_serpro_agency_options_cached(
    config: EnvironmentConfig,
    normalized_code: str,
) -> tuple[SerproAgencyOption, ...]:
    query = """
        SELECT DISTINCT
            agency.id,
            agency.code,
            agency.name,
            sub.id,
            sub.code,
            sub.name,
            upag.id,
            upag.code,
            upag.name
        FROM serpro_agencies agency
        JOIN serpro_agency_subs sub
            ON sub.serpro_agency_id = agency.id
        JOIN serpro_agency_sub_upags upag
            ON upag.serpro_agency_sub_id = sub.id
        WHERE agency.deleted_at IS NULL
          AND sub.deleted_at IS NULL
          AND upag.deleted_at IS NULL
          AND COALESCE(agency.enabled, TRUE) = TRUE
          AND COALESCE(sub.enabled, TRUE) = TRUE
          AND COALESCE(upag.enabled, TRUE) = TRUE
          AND (
              agency.code = %s
              OR sub.code = %s
              OR upag.code = %s
          )
        ORDER BY agency.id, sub.id, upag.id;
    """

    with pooled_connection(config) as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, (normalized_code, normalized_code, normalized_code))
            rows = cursor.fetchall()

    return tuple(
        SerproAgencyOption(
            agency_id=str(row[0]),
            agency_code=str(row[1]),
            agency_name=str(row[2]),
            sub_id=str(row[3]),
            sub_code=str(row[4]),
            sub_name=str(row[5]),
            upag_id=str(row[6]),
            upag_code=str(row[7]),
            upag_name=str(row[8]),
        )
        for row in rows
    )
