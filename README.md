# RetPack Portal (CT POC)

Customer-facing intake portal for returnable packaging (empty keg returns) for ABI International Supply Chain, Europe.
Requirements: [`RETPACK_REQUIREMENTS.md`](RETPACK_REQUIREMENTS.md). Plan and status: [`RETPACK_PLAN.md`](RETPACK_PLAN.md).

Phase A (mock POC) is implemented: all three screens run locally with no workspace and no credentials.

## Quick start

```bash
uv sync --all-extras
make run-mock
```

Open http://localhost:8501. Use the **Demo user** switcher in the sidebar:

| User | Role | Sees |
|---|---|---|
| `anna@northsea-distribution.example` | customer, accounts A1 + A2 | New request, My requests |
| `bram@rhine-logistics.example` | customer, account B1 | New request, My requests |
| `carla@baltic-bev.example` | customer, account C1 | New request, My requests |
| `ops1@abi.example`, `ops2@abi.example` | internal | Request queue |

Demo data lives in `config/mock/` (accounts, SKUs, sales orgs, balances, users) and is seeded with eleven requests
covering every status, including one with an unreadable (scanned) PDF and one dead-lettered CPI call.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `RETPACK_SUBMISSION_BACKEND` | `mock` | `mock` \| `delta` \| `lakebase` (only `mock` is wired until Phase B) |
| `RETPACK_FIELD_SPEC` | `config/fields/placeholder.yaml` | Field specification (FR-03). Real spec arrives as `abi_v1.yaml` in Phase C |
| `RETPACK_ATTACHMENT_POLICY` | `config/attachments.yaml` | Document types, cardinality, size limit (FR-04) |
| `RETPACK_MOCK_DATA_DIR` | `config/mock` | Reference data and users for the mock backend |
| `RETPACK_ATTACHMENT_DIR` | `.retpack_attachments` | Local PDF store for the mock backend |
| `RETPACK_MOCK_USER` | unset | Default signed-in email for local runs |
| `RETPACK_MOCK_SEED` | `1` | Seed the demo requests on start |

## Layout

```
src/retpack_core/      domain models, field-spec validation, event fold, ports, services  (no Databricks / Streamlit imports)
src/retpack_adapters/  mock repositories, local attachment store, identity providers, factory
src/retpack_ui/        Streamlit entry point, three pages, rendering components
src/retpack_jobs/      CPI dispatch job (Phase C)
config/                field spec, attachment policy, mock data
migrations/            delta/ and lakebase/ DDL (Phase B)
tests/                 unit, contract (parametrized over backends), isolation (FR-02 gate), ui (AppTest)
```

## Development

```bash
make check            # ruff, mypy, pytest with coverage gate (80%)
make test             # tests only
make contract-delta   # contract + isolation suites against Delta (needs a workspace; Phase B)
make contract-lakebase
```

The isolation suite in `tests/isolation/` is the FR-02 release gate. It runs against every backend the contract suite
knows about and includes a static check that no repository method can be called without a `Principal`.

`tests/unit/test_core_purity.py` fails the build if any Databricks, Streamlit or database-driver import creeps into
`retpack_core`.
