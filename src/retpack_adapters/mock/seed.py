"""Deterministic demo submissions covering every status, for the mock backend."""

from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any

from retpack_core import events
from retpack_core.events import SubmissionEvent
from retpack_core.ports import AttachmentStore, SubmissionRepository
from retpack_core.principal import Principal, Role

BASE_TIME = datetime(2026, 8, 20, 9, 0, tzinfo=UTC)
OPS = "ops1@abi.example"
SEED_PRINCIPAL = Principal(email="seed@system.local", account_ids=frozenset(), role=Role.SYSTEM)

ANNA = "anna@northsea-distribution.example"
BRAM = "bram@rhine-logistics.example"
CARLA = "carla@baltic-bev.example"


def _sc(account: str, actor: str, sku: str, qty: int, dest: str, pdfs: list[str], steps: list[tuple[Any, ...]]) -> dict[str, Any]:
    return {"account": account, "actor": actor, "sku": sku, "qty": qty, "dest": dest, "pdfs": pdfs, "steps": steps}


# steps: ("overwrite", field, new) | ("validate",) | ("dispatch",) | ("cpi_ok", ref) | ("cpi_fail", error, terminal) | ("credit_note", no, outcome)
_SCENARIOS: list[dict[str, Any]] = [
    _sc("A1", ANNA, "KEG50", 48, "Antwerp", ["sample.pdf"], []),
    _sc("A1", ANNA, "KEG30", 20, "Rotterdam", ["scanned.pdf"], []),
    _sc("A1", ANNA, "KEG20", 12, "Antwerp", [], [("overwrite", "quantity", 14)]),
    _sc("A1", ANNA, "KEG50S", 60, "Hamburg", ["sample.pdf"], [("validate",)]),
    _sc(
        "A1", ANNA, "KEG50", 96, "Antwerp", ["sample.pdf"], [("validate",), ("dispatch",), ("cpi_ok", "RO-7000123"), ("credit_note", "CN-2026-0451", "issued")]
    ),
    _sc("A2", ANNA, "KEG10", 8, "Antwerp", [], []),
    _sc("B1", BRAM, "KEG50", 120, "Hamburg", ["sample.pdf"], [("overwrite", "sales_org", "3000"), ("validate",)]),
    _sc("B1", BRAM, "PAL_EU", 33, "Hamburg", [], [("validate",), ("dispatch",)]),
    _sc(
        "B1",
        BRAM,
        "KEG30",
        40,
        "Le Havre",
        ["scanned.pdf"],
        [("validate",), ("dispatch",), ("cpi_fail", "CPI 504 gateway timeout", False), ("cpi_fail", "CPI 400 unknown sold-to", True)],
    ),
    _sc("C1", CARLA, "KEG50S", 24, "Le Havre", ["sample.pdf"], [("validate",), ("dispatch",), ("cpi_ok", "RO-7000098")]),
    _sc("C1", CARLA, "KEG20", 16, "Rotterdam", [], []),
]


def seed_demo(repo: SubmissionRepository, store: AttachmentStore, data_dir: Path) -> None:
    """Append the demo scenarios to ``repo``; PDFs are stored through ``store``."""
    pdf_bytes = {name: (data_dir / name).read_bytes() for name in ("sample.pdf", "scanned.pdf")}
    for i, sc in enumerate(_SCENARIOS, start=1):
        sid = f"0190f0a0-0000-7000-8000-{i:012d}"
        t0 = BASE_TIME + timedelta(days=i, hours=i % 5)
        customer = Principal(email=sc["actor"], account_ids=frozenset({sc["account"]}), role=Role.CUSTOMER)
        metas = [
            store.put(customer, sid, doc_type="delivery_note" if k == 0 else "other", seq=k + 1, filename=name, stream=BytesIO(pdf_bytes[name]))
            for k, name in enumerate(sc["pdfs"])
        ]
        log: list[SubmissionEvent] = [events.submitted(sid, sc["account"], actor=sc["actor"], values=_values(i, sc), attachments=metas, at=t0)]
        repo.append_event(customer, sid, 0, log[0])
        for step in sc["steps"]:
            event = _event_for(step, sid, sc["account"], seq=len(log) + 1, at=t0 + timedelta(hours=len(log)))
            repo.append_event(SEED_PRINCIPAL, sid, len(log), event)
            log.append(event)


def _values(i: int, sc: dict[str, Any]) -> dict[str, Any]:
    return {
        "account_id": sc["account"],
        "sku_code": sc["sku"],
        "container_no": f"{4000000000 + i * 7919:010d}",
        "seal_no": f"SL-{i:04d}",
        "bl_no": f"BL-{2026}-{i:05d}",
        "destination": sc["dest"],
        "pickup_date": (BASE_TIME + timedelta(days=i + 10)).date().isoformat(),
        "quantity": sc["qty"],
        "weight_tons": str(round(sc["qty"] * 0.062, 2)),
        "remarks": "Demo data" if i % 2 else "",
    }


def _event_for(step: tuple[Any, ...], sid: str, account: str, *, seq: int, at: datetime) -> SubmissionEvent:
    kind = step[0]
    if kind == "overwrite":
        return events.field_overwritten(sid, account, actor=OPS, seq=seq, field=step[1], prior=None if step[1] == "sales_org" else 12, new=step[2], at=at)
    if kind == "validate":
        return events.validated(sid, account, actor=OPS, seq=seq, at=at)
    if kind == "dispatch":
        return events.cpi_dispatched(sid, account, seq=seq, idempotency_key=f"{sid}:{seq - 1}", attempt=1, at=at)
    if kind == "cpi_ok":
        return events.cpi_succeeded(sid, account, seq=seq, cpi_reference=step[1], attempt=1, at=at)
    if kind == "cpi_fail":
        return events.cpi_failed(sid, account, seq=seq, error=step[1], attempt=seq - 3, terminal=step[2], at=at)
    if kind == "credit_note":
        return events.credit_note_recorded(sid, account, seq=seq, credit_note_no=step[1], outcome=step[2], at=at)
    raise ValueError(f"unknown seed step {kind!r}")
