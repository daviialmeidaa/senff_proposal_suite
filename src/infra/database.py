from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass

import psycopg2
from psycopg2.extensions import connection as PsycopgConnection

from src.core.config import EnvironmentConfig


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


def test_connection(config: EnvironmentConfig) -> None:
    with closing(connect(config)) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1;")
            cursor.fetchone()


def fetch_agreements(config: EnvironmentConfig) -> list[Agreement]:
    query = """
        SELECT id, name
        FROM agreements
        WHERE name IS NOT NULL
        ORDER BY id ASC;
    """

    with closing(connect(config)) as conn:
        with conn.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()

    return [Agreement(id=str(row[0]), name=row[1]) for row in rows]


def fetch_products(config: EnvironmentConfig) -> list[Product]:
    query = """
        SELECT id, name
        FROM products
        WHERE name IS NOT NULL
        ORDER BY id ASC;
    """

    with closing(connect(config)) as conn:
        with conn.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()

    return [Product(id=str(row[0]), name=row[1]) for row in rows]


def fetch_sale_modalities(config: EnvironmentConfig) -> list[SaleModality]:
    query = """
        SELECT id, name
        FROM sale_modalities
        WHERE name IS NOT NULL
        ORDER BY id ASC;
    """

    with closing(connect(config)) as conn:
        with conn.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()

    return [SaleModality(id=str(row[0]), name=row[1]) for row in rows]


def fetch_withdraw_types(config: EnvironmentConfig) -> list[WithdrawType]:
    query = """
        SELECT id, name
        FROM withdraw_types
        WHERE name IS NOT NULL
        ORDER BY id ASC;
    """

    with closing(connect(config)) as conn:
        with conn.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()

    return [WithdrawType(id=str(row[0]), name=row[1]) for row in rows]


def fetch_serpro_agency_options(
    config: EnvironmentConfig,
    orgao_code: str,
) -> list[SerproAgencyOption]:
    normalized_code = orgao_code.strip()
    if not normalized_code:
        return []

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

    with closing(connect(config)) as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, (normalized_code, normalized_code, normalized_code))
            rows = cursor.fetchall()

    return [
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
    ]

