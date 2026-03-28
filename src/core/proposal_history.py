from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Any


@dataclass(frozen=True)
class FlowStage:
    id: str
    code: str
    name: str
    status: str


@dataclass(frozen=True)
class ProposalFlow:
    proposal_id: str
    flow_id: str
    stages: list[FlowStage]


@dataclass
class ProposalRecord:
    environment_key: str
    created_at: str

    # Simulation identifiers
    simulation_id: str
    simulation_code: str
    client_id: str

    # Proposal identifiers
    proposal_id: str
    proposal_code: str
    contract_code: str

    # Input context
    agreement_id: str
    product_id: str
    sale_modality_id: str
    withdraw_type_id: str
    processor_code: str

    # Client context
    client_name: str
    client_document: str
    client_phone: str
    benefit_number: str

    # Generated data
    contract_document_type: str
    contract_document_number: str
    email: str

    # Pipeline flow
    flow: ProposalFlow | None = None

    # Raw API responses (for future pipeline validation)
    simulation_response: dict[str, Any] = field(default_factory=dict, repr=False)
    proposal_response: dict[str, Any] = field(default_factory=dict, repr=False)


_HISTORY_LOCK = Lock()
_HISTORY: dict[str, list[ProposalRecord]] = {}


def record_proposal(record: ProposalRecord) -> int:
    with _HISTORY_LOCK:
        env_records = _HISTORY.setdefault(record.environment_key, [])
        env_records.append(record)
        return len(env_records)


def get_history(environment_key: str) -> list[ProposalRecord]:
    with _HISTORY_LOCK:
        return list(_HISTORY.get(environment_key, []))


def get_history_record(environment_key: str, index: int) -> ProposalRecord | None:
    with _HISTORY_LOCK:
        records = _HISTORY.get(environment_key, [])
        if 1 <= index <= len(records):
            return records[index - 1]
        return None


def get_all_history() -> dict[str, list[ProposalRecord]]:
    with _HISTORY_LOCK:
        return {key: list(records) for key, records in _HISTORY.items()}


def clear_history() -> None:
    with _HISTORY_LOCK:
        _HISTORY.clear()


def count(environment_key: str) -> int:
    with _HISTORY_LOCK:
        return len(_HISTORY.get(environment_key, []))


def update_record_flow(
    environment_key: str,
    index: int,
    flow: ProposalFlow | None,
) -> ProposalRecord | None:
    with _HISTORY_LOCK:
        records = _HISTORY.get(environment_key, [])
        if 1 <= index <= len(records):
            records[index - 1].flow = flow
            return records[index - 1]
        return None


def extract_proposal_flow(dashboard_response: dict[str, Any]) -> ProposalFlow | None:
    rows = dashboard_response.get("rows") or []
    if not rows:
        return None

    row = rows[0]
    flow = row.get("flow") or {}
    flow_id = str(flow.get("id") or "")
    proposal_id = str(row.get("id") or "")

    stages = [
        FlowStage(
            id=str(stage.get("id") or ""),
            code=str(stage.get("code") or ""),
            name=str(stage.get("name") or ""),
            status=str(stage.get("status") or ""),
        )
        for stage in (flow.get("stages") or [])
    ]

    return ProposalFlow(
        proposal_id=proposal_id,
        flow_id=flow_id,
        stages=stages,
    )


def build_proposal_record(
    *,
    environment_key: str,
    agreement_id: str,
    product_id: str,
    sale_modality_id: str,
    withdraw_type_id: str,
    processor_code: str,
    client_name: str,
    client_document: str,
    client_phone: str,
    benefit_number: str,
    simulation_id: str,
    simulation_code: str,
    client_id: str,
    contract_document_type: str,
    contract_document_number: str,
    email: str,
    simulation_response: dict[str, Any],
    proposal_response: dict[str, Any],
    flow: ProposalFlow | None = None,
) -> ProposalRecord:
    proposal_data = proposal_response.get("data") or {}

    return ProposalRecord(
        environment_key=environment_key,
        created_at=datetime.now(timezone.utc).isoformat(),
        simulation_id=simulation_id,
        simulation_code=simulation_code,
        client_id=client_id,
        proposal_id=str(proposal_data.get("id") or ""),
        proposal_code=str(proposal_data.get("code") or ""),
        contract_code=str(proposal_data.get("contract_code") or proposal_data.get("code") or ""),
        agreement_id=agreement_id,
        product_id=product_id,
        sale_modality_id=sale_modality_id,
        withdraw_type_id=withdraw_type_id,
        processor_code=processor_code,
        client_name=client_name,
        client_document=client_document,
        client_phone=client_phone,
        benefit_number=benefit_number,
        contract_document_type=contract_document_type,
        contract_document_number=contract_document_number,
        email=email,
        flow=flow,
        simulation_response=simulation_response,
        proposal_response=proposal_response,
    )

