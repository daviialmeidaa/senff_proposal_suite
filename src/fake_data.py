from __future__ import annotations

from faker import Faker


class FakeDataService:
    def __init__(self) -> None:
        self.fake = Faker("pt_BR")

    def generate_name(self) -> str:
        return self.fake.name()

    def generate_document(self) -> str:
        if hasattr(self.fake, "cpf"):
            return self.fake.cpf().replace(".", "").replace("-", "")
        return self.fake.numerify(text="###########")

    def generate_phone(self) -> str:
        return self.fake.numerify(text="489########")

    def generate_numeric_code(self, length: int = 8) -> str:
        safe_length = max(1, length)
        return self.fake.numerify(text="#" * safe_length)

    def generate_password(self) -> str:
        return self.fake.password(length=10, special_chars=False)
