from __future__ import annotations

import re
import unicodedata
from datetime import date
from random import choice

from faker import Faker


HONORIFICS = {
    "sr",
    "sra",
    "srta",
    "dr",
    "dra",
    "mr",
    "mrs",
    "ms",
    "prof",
    "professor",
    "professora",
}


class FakeDataService:
    def __init__(self) -> None:
        self.fake = Faker("pt_BR")

    def generate_name(self) -> str:
        parts = [
            self.fake.first_name(),
            self.fake.last_name(),
            self.fake.last_name(),
        ]
        return self._sanitize_words(" ".join(parts), uppercase=False)

    def generate_parent_name(self) -> str:
        return self.generate_name()

    def generate_document(self) -> str:
        if hasattr(self.fake, "cpf"):
            return self._digits_only(self.fake.cpf())
        return self.fake.numerify(text="###########")

    def generate_phone(self) -> str:
        return self.fake.numerify(text="489########")

    def generate_contract_document_type(self) -> str:
        return choice(["rg", "cnh"])

    def generate_numeric_code(self, length: int = 8) -> str:
        safe_length = max(1, length)
        return self.fake.numerify(text="#" * safe_length)

    def generate_password(self) -> str:
        return self.fake.password(length=10, special_chars=False)

    def generate_birth_date(self, minimum_age: int = 25, maximum_age: int = 70) -> str:
        return self.fake.date_of_birth(
            minimum_age=minimum_age,
            maximum_age=maximum_age,
        ).strftime("%Y-%m-%d")

    def generate_email(self, base_name: str) -> str:
        normalized_name = self._sanitize_words(base_name, uppercase=False).lower().replace(" ", ".")
        normalized_name = normalized_name.strip(".") or "cliente.teste"
        suffix = self.generate_numeric_code(4)
        return f"{normalized_name}.{suffix}@example.com"

    def generate_city(self) -> str:
        return self._sanitize_words(self.fake.city(), uppercase=False)

    def generate_street(self) -> str:
        return self._sanitize_words(self.fake.street_name(), uppercase=False)

    def generate_postal_code(self) -> str:
        postal_code = self._digits_only(self.fake.postcode())
        return postal_code[:8].ljust(8, "0")

    def generate_address_number(self) -> str:
        return str(self.fake.random_int(min=1, max=9999))

    def generate_address_complement(self) -> str:
        return choice(["CASA", "APTO 1", "BLOCO A", "FUNDOS"])

    def generate_district(self) -> str:
        return self._sanitize_words(f"Bairro {self.fake.last_name()}", uppercase=False)

    def generate_contract_document_number(
        self,
        document_type: str,
        *,
        exclude: str = "",
    ) -> str:
        normalized_type = str(document_type or "").strip().lower()
        excluded_digits = self._digits_only(exclude)

        while True:
            if normalized_type == "cnh":
                candidate = self.generate_numeric_code(11)
            else:
                candidate = self.generate_numeric_code(9)
            if candidate != excluded_digits:
                return candidate

    def generate_document_issuer(self) -> str:
        return choice(["SSP", "DETRAN", "SESP"])

    def generate_document_expedition_date(self) -> str:
        return self.fake.date_between(start_date="-20y", end_date="-2y").strftime("%Y-%m-%d")

    def generate_agency(self) -> str:
        return self.generate_numeric_code(4)

    def generate_agency_digit(self) -> str:
        return self.generate_numeric_code(1)

    def generate_account(self) -> str:
        return self.generate_numeric_code(8)

    def generate_account_digit(self) -> str:
        return self.generate_numeric_code(1)

    def _sanitize_words(self, value: str, *, uppercase: bool) -> str:
        normalized = unicodedata.normalize("NFKD", str(value or ""))
        ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
        cleaned = re.sub(r"[^A-Za-z ]+", " ", ascii_value)
        tokens = [token for token in cleaned.split() if token.lower() not in HONORIFICS]
        fallback = "Cliente Teste"
        if not tokens:
            tokens = fallback.split()
        joined = " ".join(tokens)
        return joined.upper() if uppercase else joined.title()

    def _digits_only(self, value: str) -> str:
        return "".join(character for character in str(value) if character.isdigit())

