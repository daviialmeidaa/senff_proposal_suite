from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any

import gspread
from gspread.utils import ValueRenderOption
from google.oauth2.service_account import Credentials


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CREDENTIALS_FILE = PROJECT_ROOT / "credentials.json"
SPREADSHEET_ID = "18gmFibQE9dzbBkyuZFW3_kCvpAZc1arKmA0XFYGE5d4"
PROCESSOR_SHEET_MAP = {
    "dataprev": "DATAPREV",
    "cip": "CIP",
    "serpro": "SERPRO",
    "zetra": "ZETRA",
    "econsig-zetra": "ZETRA",
}
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

_CLIENT_LOCK = Lock()
_PROCESSOR_CACHE_LOCK = Lock()
_GSPREAD_CLIENT: gspread.Client | None = None
_GSPREAD_SPREADSHEET = None
_PROCESSOR_DATA_CACHE: dict[str, Any] = {}


class GoogleSheetsError(RuntimeError):
    pass


class NoEligibleSheetRecordError(GoogleSheetsError):
    pass


@dataclass(frozen=True)
class ProcessorSheetData:
    processor_code: str
    worksheet_name: str
    records: list[dict[str, Any]]


@dataclass(frozen=True)
class SelectedSheetRecord:
    processor_code: str
    worksheet_name: str
    product_type: str
    balance_field: str
    balance_value: str
    matricula: str
    cpf: str
    nome: str = ""
    orgao: str = ""
    senha: str = ""
    matching_records_count: int = 0
    selected_record_index: int = 0
    selected_record_number: int = 1


class GoogleSheetsService:
    def __init__(self) -> None:
        if not CREDENTIALS_FILE.exists():
            raise GoogleSheetsError(
                f"Arquivo de credenciais nao encontrado em {CREDENTIALS_FILE}"
            )

        self.client = self._get_client()

    def load_processor_data(
        self,
        processor_code: str,
        *,
        refresh: bool = False,
    ) -> ProcessorSheetData:
        normalized_processor = processor_code.strip().lower()
        worksheet_name = PROCESSOR_SHEET_MAP.get(normalized_processor)
        if not worksheet_name:
            raise GoogleSheetsError(
                f"Nao existe uma aba mapeada para a processadora '{processor_code}'."
            )

        if not refresh:
            with _PROCESSOR_CACHE_LOCK:
                cached = _PROCESSOR_DATA_CACHE.get(worksheet_name)
            if cached is not None:
                return cached

        try:
            spreadsheet = self._get_spreadsheet()
            worksheet = spreadsheet.worksheet(worksheet_name)
            rows = worksheet.get_all_records(
                value_render_option=ValueRenderOption.formatted,
                numericise_ignore=["all"],
            )
        except gspread.exceptions.WorksheetNotFound as exc:
            raise GoogleSheetsError(
                f"A aba '{worksheet_name}' nao foi encontrada na planilha."
            ) from exc
        except Exception as exc:
            raise GoogleSheetsError(
                f"Falha ao consultar a planilha do Google Sheets: {exc}"
            ) from exc

        valid_rows = [row for row in rows if str(row.get("Cpf", "")).strip()]
        mapped_rows = [self._map_row(row, worksheet_name) for row in valid_rows]
        processor_data = ProcessorSheetData(
            processor_code=normalized_processor,
            worksheet_name=worksheet_name,
            records=mapped_rows,
        )

        with _PROCESSOR_CACHE_LOCK:
            _PROCESSOR_DATA_CACHE[worksheet_name] = processor_data
        return processor_data

    def select_record_from_data(
        self,
        processor_data: ProcessorSheetData,
        product_name: str,
        record_index: int = 0,
    ) -> SelectedSheetRecord:
        worksheet_name = processor_data.worksheet_name
        product_type = self._resolve_product_type(product_name)

        if worksheet_name == "DATAPREV":
            balance_field = product_type
            matching_records = [
                record
                for record in processor_data.records
                if record.get("status", "").strip().lower() == "ok"
                and self._parse_balance(
                    record.get("saldoProdutos", {}).get(balance_field, 0)
                ) > 0
            ]
        elif worksheet_name in {"CIP", "SERPRO"}:
            balance_field = product_type
            matching_records = [
                record
                for record in processor_data.records
                if self._parse_balance(
                    record.get("saldoProdutos", {}).get(balance_field, 0)
                ) > 0
            ]
        elif worksheet_name == "ZETRA":
            balance_field = "RCC"
            matching_records = [
                record
                for record in processor_data.records
                if self._parse_balance(
                    record.get("saldoProdutos", {}).get(balance_field, 0)
                ) > 0
            ]
        else:
            raise GoogleSheetsError(
                f"Nao existem regras de selecao configuradas para a aba '{worksheet_name}'."
            )

        if not matching_records:
            raise NoEligibleSheetRecordError(
                f"Nenhum registro elegivel foi encontrado na aba '{worksheet_name}' para o produto '{product_name}'."
            )

        normalized_record_index = max(int(record_index or 0), 0) % len(matching_records)
        selected_record = matching_records[normalized_record_index]
        return SelectedSheetRecord(
            processor_code=processor_data.processor_code,
            worksheet_name=worksheet_name,
            product_type=product_type,
            balance_field=balance_field,
            balance_value=str(selected_record.get("saldoProdutos", {}).get(balance_field, "")),
            matricula=str(selected_record.get("matricula", "")),
            cpf=str(selected_record.get("cpf", "")),
            nome=str(selected_record.get("nome", "")),
            orgao=str(selected_record.get("orgao", "")),
            senha=str(selected_record.get("senha", "")),
            matching_records_count=len(matching_records),
            selected_record_index=normalized_record_index,
            selected_record_number=normalized_record_index + 1,
        )

    def _map_row(self, row: dict[str, Any], worksheet_name: str) -> dict[str, Any]:
        return {
            "matricula": str(row.get("Matricula/Beneficio", "")).lstrip("'"),
            "cpf": str(row.get("Cpf", "")).lstrip("'"),
            "orgao": str(row.get("Orgao", "")),
            "senha": str(row.get("Senha", "")),
            "saldoProdutos": {
                "RCC": row.get("Saldo Atualizado RCC", 0),
                "RMC": row.get("Saldo Atualizado RMC", 0),
            },
            "elegibleLoan": str(row.get("Elegible Loan", "")) if worksheet_name == "DATAPREV" else "",
            "nome": str(row.get("Nome", "")) if worksheet_name == "DATAPREV" else "",
            "status": str(row.get("Status", "")) if worksheet_name == "DATAPREV" else "",
        }

    def _resolve_product_type(self, product_name: str) -> str:
        normalized_product = product_name.upper()
        if "RCC" in normalized_product:
            return "RCC"
        if "RMC" in normalized_product:
            return "RMC"
        raise GoogleSheetsError(
            "As regras atuais da planilha estao definidas apenas para produtos RCC e RMC."
        )

    def _parse_balance(self, value: Any) -> float:
        if isinstance(value, (int, float)):
            return float(value)

        text = str(value).strip()
        if not text or text.lower() == "carregando...":
            return 0.0

        normalized = (
            text.replace("R$", "")
            .replace(".", "")
            .replace(",", ".")
            .strip()
        )
        try:
            return float(normalized)
        except ValueError:
            return 0.0

    def _get_client(self) -> gspread.Client:
        global _GSPREAD_CLIENT

        with _CLIENT_LOCK:
            if _GSPREAD_CLIENT is not None:
                return _GSPREAD_CLIENT

            credentials = Credentials.from_service_account_file(
                str(CREDENTIALS_FILE),
                scopes=GOOGLE_SCOPES,
            )
            _GSPREAD_CLIENT = gspread.authorize(credentials)
            return _GSPREAD_CLIENT

    def _get_spreadsheet(self):
        global _GSPREAD_SPREADSHEET

        with _CLIENT_LOCK:
            if _GSPREAD_SPREADSHEET is not None:
                return _GSPREAD_SPREADSHEET
            _GSPREAD_SPREADSHEET = self.client.open_by_key(SPREADSHEET_ID)
            return _GSPREAD_SPREADSHEET
