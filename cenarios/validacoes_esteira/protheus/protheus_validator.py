"""
Validações de esteira — Etapas Protheus.

Encapsula as duas fases de validação do Protheus em uma única classe:

  Fase 1 — Formalização  (stage_code = "protheus")
  Fase 2 — Emissão       (stage_code = "protheus-issuance")

Uso típico (dentro do execution engine ou em testes):

    validator = ProtheusStageValidator(config=config, cpf=cpf)
    result1, cutoff_id, client_code = validator.validate_formalization(
        correlation_id=correlation_id
    )
    result2 = validator.validate_issuance(
        correlation_id=correlation_id,
        proposal_id=proposal_id,
        codigo_criacao=codigo_criacao,
    )

O estado compartilhado entre as fases (client_code, last_log_id) é armazenado
internamente após a Fase 1 e reutilizado automaticamente pela Fase 2 quando
disponível.
"""

from __future__ import annotations

from src.core.config import EnvironmentConfig
from src.core.proposal_history import ProtheusValidationResult
from src.services.protheus_validator import (
    validate_protheus_formalization,
    validate_protheus_issuance,
)


class ProtheusStageValidator:
    """
    Validador das etapas Protheus da esteira de crédito consignado.

    Instanciar uma vez por proposta e chamar os métodos de validação na ordem
    correta: primeiro `validate_formalization`, depois `validate_issuance`.
    O estado interno herdado (client_code e last_log_id) é passado
    automaticamente para a Fase 2.
    """

    def __init__(self, *, config: EnvironmentConfig, cpf: str) -> None:
        self.config = config
        self.cpf = cpf

        # Estado herdado da Fase 1 para a Fase 2
        self._client_code: str | None = None
        self._last_log_id: int = 0

    # ------------------------------------------------------------------
    # Fase 1 — Formalização (stage_code = "protheus")
    # ------------------------------------------------------------------
    def validate_formalization(
        self,
        *,
        correlation_id: str,
    ) -> tuple[ProtheusValidationResult, int, str | None]:
        """
        Valida a etapa 'protheus' (formalização):
          - Confirma presença do CPF em protheus_client_codes
          - Verifica log ATUALIZAR com <STATUS>true</STATUS> em protheus_logs
          - Chama SOAP VALFOR externamente para confirmar o CPF no Protheus

        Armazena internamente client_code e last_log_id para herdar à Fase 2.

        Returns:
            (ProtheusValidationResult, last_log_id, client_code)
        """
        result, cutoff_id, client_code = validate_protheus_formalization(
            config=self.config,
            correlation_id=correlation_id,
            cpf=self.cpf,
        )
        self._client_code = client_code
        self._last_log_id = cutoff_id
        return result, cutoff_id, client_code

    # ------------------------------------------------------------------
    # Fase 2 — Emissão (stage_code = "protheus-issuance")
    # ------------------------------------------------------------------
    def validate_issuance(
        self,
        *,
        correlation_id: str,
        proposal_id: str | int,
        codigo_criacao: str,
        stage_already_approved: bool = False,
        protheus_client_code: str | None = None,
        last_protheus_id: int | None = None,
    ) -> ProtheusValidationResult:
        """
        Valida a etapa 'protheus-issuance' (emissão):
          - Verifica log INCPAGARSE com <STATUS>true</STATUS> em protheus_logs
          - Aplica bypass 'Sem Saque' se stage_already_approved e log ausente
          - Chama SOAP INCPAGARSE como prova de realidade (espera fault de duplicata)
          - Confirma registro na tabela protheus_issuance

        client_code e last_log_id são herdados automaticamente da Fase 1 quando
        disponíveis; os parâmetros explícitos têm precedência se fornecidos.

        Returns:
            ProtheusValidationResult
        """
        resolved_client_code = protheus_client_code if protheus_client_code is not None else self._client_code
        resolved_last_id = last_protheus_id if last_protheus_id is not None else self._last_log_id

        return validate_protheus_issuance(
            config=self.config,
            correlation_id=correlation_id,
            proposal_id=proposal_id,
            codigo_criacao=codigo_criacao,
            cpf=self.cpf,
            last_protheus_id=resolved_last_id,
            stage_already_approved=stage_already_approved,
            protheus_client_code=resolved_client_code,
        )
