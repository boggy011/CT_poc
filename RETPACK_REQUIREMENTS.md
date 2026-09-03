# ABI RetPack Portal — Implementation Requirements

Derived from *ABI RetPack Portal — Requirements & Development Plan v0.1* (CT Data Practice, 1 Sep 2026).

**Two kinds of statement in this document:**

- `[ABI]` — stated in the source requirements. Do not change without ABI sign-off.
- `[CT]` — CT design decision. Ours to change; rationale given.

---

## 1. What this is

A customer-facing intake portal for returnable packaging (empty keg returns), International Supply Chain scope, Europe.

~50 third-party distributors submit return requests. A 3-person internal ABI team validates or corrects them. Validated requests trigger return-order creation in SAP ECC via existing CPI endpoints.

`[ABI]` This is an **order portal**, deliberately separate from the complaint flow (complaints go to ServiceNow, out of scope).

`[ABI]` The portal does **not** validate business correctness. Humans plus an existing ABI AI solution do that.

### Scale

| Dimension | Value |
|---|---|
| External customers | ~50 |
| Internal users | 3 |
| Sales organizations | 4 |
| SKUs per customer account | 4–5 |
| Concurrency | Low |
| Screens | 2 external + 1 internal |

`[ABI]` Screen count is an explicit cost guardrail. Target platform run cost ≈ $5K/yr.

---

## 2. Scope

### In — Wave 1

R01 (request intake) + CN2 (credit note / status) + display-only per-customer keg balance.

### Out — Wave 1

R02, R03 (order changes), GR1, GR2 (goods receipt), GSN1 — deferred pending ABI mapping review, **not a final exclusion**. Also out: intermediate SAP statuses (return-order no., shipment no.), reconciliation drill-down, pre-portal history migration, complaint portal, email/AI intake channel, portal-side error detection, China/Korea/Vietnam scale-out.

---

## 3. Functional requirements

### FR-01 — Login & identity `[ABI]`

Email-based login. Each customer maps to their account (payer / sold-to).

- Signed-in identity comes from the platform, never from client input.
- Email → account resolution happens server-side on **every** request.
- Provisioning process for customer emails is undefined — see questions doc Q1.

### FR-02 — Tenant isolation `[ABI]` — non-negotiable

A customer sees only their own requests and shipments.

`[CT]` Enforced in two independent layers:

1. Repository layer: no query method is callable without a resolved `Principal`. No method accepts an optional customer filter. Unfiltered queries must be structurally impossible to express.
2. Unity Catalog row filters under user authorization, where available.

`[CT]` Isolation is covered by a dedicated contract test suite and is a **release gate**, not a checklist item.

### FR-03 — Intake form (external) `[ABI]`

~30 manual fields per the ABI mapping file. Includes account selection, SKU dropdown (4–5 per account, sourced from Databricks), container no., seal no., BL no., destination, quantities, dates.

- Mandatory-field enforcement required.
- Per-field format rules where defined (e.g. 10-digit container no.).
- Free text acceptable where no rule is defined.

`[CT]` **Fields are configuration, not code.** One YAML spec per field drives the renderer, client-side hints, and server-side validation:

```yaml
- name: container_no
  label: Container number
  type: string
  section: shipment
  order: 10
  required: true
  pattern: '^\d{10}$'
  max_length: 10
```

Rationale: the real field list arrives late (ABI mapping Excel). Adding or tightening a rule must be a config commit, not a code change. Undefined rules default to free text.

`[CT]` Dropdown sources are declared in the same spec and resolved through the reference repository.

### FR-04 — PDF attachments `[ABI]`

PDF only. Stored and linked to the request for the existing AI cross-check.

`[CT]` The portal treats PDFs as opaque bytes. It does not parse or interpret them — structure is the AI team's concern. Attachment metadata is modelled as typed rows so cardinality rules can be added later as config:

```
attachment(
  submission_id, doc_type, seq,
  original_filename, storage_path, sha256,
  size_bytes, page_count, has_text_layer,
  uploaded_at, uploaded_by
)
```

- `sha256` gives duplicate detection (the source doc's Phase-3 test asks for it).
- `has_text_layer` is a cheap upload-time check. A scanned/photographed PDF has no extractable text, so the ABI AI cross-check silently gets nothing and the request drops to manual handling. `[CT]` Surface as a **warning, not a block** — blocking would breach FR-06.
- PDF enforcement is server-side by magic bytes, not by file extension.
- Bytes stream to a UC Volume immediately; never buffered wholesale in app memory, never stored in the transactional database.

Attachment cardinality and doc types are unspecified in the source — see questions doc Q2.

### FR-05 — Submission to Databricks `[ABI]`

On submit, the request lands in Databricks submission table(s). Databricks is both source (reference data) and target (intake).

`[CT]` Submissions are modelled as an **append-only event log**, with current state derived as a view:

```
submission_event(
  submission_id, seq, event_type, actor, actor_role,
  occurred_at, payload
)
```

Rationale, three problems solved at once:
- Satisfies NFR-05 audit (original vs. corrected values retained by construction).
- Avoids `UPDATE` on Delta, which is the wrong primitive for per-row status changes.
- Works identically on Delta and on Postgres, keeping the backend swappable.

`[CT]` Every user action must collapse into **one** event append. Delta has no cross-table transactions; the interface therefore never exposes `begin`/`commit`.

`[CT]` IDs are generated in application code — UUIDv7 or ULID, time-ordered. Delta has no reliable sequence primitive, and retrofitting ID generation later is expensive.

### FR-06 — No portal-side error detection `[ABI]`

Validation is the internal team plus the existing ABI AI cross-check. The portal enforces format and mandatory rules only. It does not judge business correctness.

### FR-07 — Status view (external) `[ABI]`

Customer sees own requests with status (validated / not validated) plus credit-note outcome (CN2). Read-only. No customer edits after validation.

Exact status enum is undefined in the source — see questions doc Q3. Must be frozen before the GAC AI team builds against it.

### FR-08 — History `[ABI]`

Submission history visible. Retention horizon 3–5 years, to be fixed. No migration of pre-portal history in Wave 1.

### FR-09 — Internal team view `[ABI]`

Role-gated second view for the 3-person team.

- Request queue, fields auto-populated from Databricks (e.g. sales-org dropdown of 4).
- Right to overwrite **any** customer-entered field.
- Validate action releases the request downstream.
- Customers are never asked to self-correct typos.

`[CT]` Overwrites are appended as events carrying both prior and new value, with actor identity. Nothing is destructively updated.

### FR-10 — SAP handoff `[ABI]`

Validated request triggers return-order creation in ECC through existing CPI endpoints and triggers. No new integration build.

`[CT]` **Never call CPI from the request thread.** Databricks Apps run a single small container shared by all users; a CPI timeout inside a handler degrades the app for everyone.

Flow: validation appends an event → a Databricks Job polls pending-validated → calls CPI with idempotency key, bounded retry, and dead-letter → appends a result event.

### FR-11 — Keg balance display `[ABI]`

Per-customer balance (shipped vs. returned), calculated in Databricks, shown as a plain number. No drill-down, no interaction. Deeper detail is served manually by the ABI team.

Calculation ownership (ABI vs. CT) is unresolved — see questions doc Q6.

---

## 4. Non-functional requirements

| ID | Requirement |
|---|---|
| NFR-01 `[ABI]` | Credential-based access; strict per-customer isolation; external publication conditional on IT security clearance |
| NFR-02 `[ABI]` | ~50 customers, 3 internal users, low concurrency, minimal compute sizing |
| NFR-03 `[ABI]` | Platform run cost ≈ $5K/yr at Wave-1 scope; scope discipline is the primary cost lever |
| NFR-04 `[ABI]` | "User-friendly but nothing extra complex". Screen count is a deliberate guardrail |
| NFR-05 `[CT]` | Preserve original customer input when the internal team overwrites (who / what / when). Satisfied by the event model |
| NFR-06 `[ABI]` | Storage retention aligned to the 3–5 year history decision |

---

## 5. Architecture

### 5.1 Layering `[CT]`

```
retpack_core/       # domain models, validation engine, repository interfaces
                    # pure Python — no streamlit, no databricks imports
retpack_adapters/   # MockSubmissionRepo | DeltaSubmissionRepo | LakebaseSubmissionRepo
                    # ReferenceRepo (Delta/UC) | VolumeAttachmentStore | LocalAttachmentStore
retpack_ui/         # streamlit pages — rendering and wiring only
```

**Rationale.** Databricks Apps cannot be published publicly — anonymous access and SSO bypass are not supported, so external customers must be provisioned as account identities via SCIM/JIT. If that clearance fails, the documented fallback is a thin external front end over secured Databricks connectivity. With this layering that fallback costs the UI layer only: put FastAPI in front of the same `retpack_core` and keep everything else.

Consequence: `retpack_core` must remain importable with zero Databricks dependencies. Treat any Databricks import creeping into it as a defect.

### 5.2 Dual persistence backend `[CT]`

Only the **transactional** store is swappable. Reference data and attachments are not.

| Concern | Store | Swappable |
|---|---|---|
| Submissions, events, status, audit | Delta *or* Lakebase Postgres | yes |
| Reference views (SKU, sales org, email↔account) | Delta / Unity Catalog | no |
| PDF attachments | UC Volume | no |

Selected by config: `RETPACK_SUBMISSION_BACKEND=mock|delta|lakebase`

**Default for Wave 1: Delta.** It needs no new ABI component approval and fits the existing data-layer ownership. Lakebase (GA since Feb 2026, with native Databricks Apps resource integration) stays implemented and tested so migration is a config flag when volumes or the scale-out justify it. Present Postgres to ABI as a Wave-2 item with a proven path, not a new component argued for against a fixed deadline.

**Semantic differences the interface must absorb:**

| | Delta | Lakebase Postgres |
|---|---|---|
| Multi-table transactions | none | full ACID |
| Concurrency | table-level optimistic, throws on conflict | row locks |
| ID generation | no reliable sequence | sequences / identity |
| Read latency | seconds + warehouse cold start | single-digit ms |

Handled by:
- Expected-version semantics instead of locking: `append_event(submission_id, expected_seq, event) -> int`. Postgres uses a unique constraint on `(submission_id, seq)`; Delta uses conditional MERGE with bounded retry. Caller sees one contract.
- No read-after-write assumption anywhere in the UI. After submit, render from the object just constructed — never round-trip. Correct on both, mandatory on Delta.

**Do not abstract:** migrations (`migrations/delta/`, `migrations/lakebase/` kept separate — a dual-emitting schema DSL costs more than the schemas and breaks on the first index or partition spec) and operational tuning (Delta needs scheduled `OPTIMIZE` for per-request insert churn; Postgres does not).

### 5.3 Contract tests `[CT]`

One suite written against the interfaces, parametrized over all three implementations:

```
tests/contract/test_submission_repository.py  → [mock, delta, lakebase]
```

Tenant-isolation cases live here, so the FR-02 release gate is satisfied by construction on whichever backend ships. This suite is also the only real proof the backend swap works rather than merely compiles.

### 5.4 Streamlit constraints `[CT]`

Workable at this scale; a hard ceiling beyond it.

- Full script rerun on every widget interaction — the 30-field intake must be inside `st.form`.
- No native routing; deep-linking a single request is awkward.
- Single container, single process, no horizontal autoscale. All users share it.
- Any long-running call in a handler blocks every user. See FR-10.

**Do not commit to the China/Korea/Vietnam scale-out on this stack** without a re-architecture line item.

---

## 6. Build sequence

**Phase A — Mock POC. Needs nothing from ABI. Start immediately.**

All three screens against `MockSubmissionRepository` with JSON fixtures and a placeholder field spec. Runs locally with `RETPACK_SUBMISSION_BACKEND=mock`, no workspace, no credentials.

This doubles as the UI mock ABI is waiting on, and gives the IT-security conversation something concrete instead of an abstraction.

**Phase B — Real adapters.** Swap mock → Delta. Deploy the identical app to the workspace. Freeze the data contract: event table, status enum, attachment linkage, reference views, balance table. Hand the frozen contract to the ABI AI team.

**Phase C — Real content.** Replace the placeholder field spec with the real ~30 fields from the ABI mapping file. Wire the internal role and the CPI job. Screens already exist.

**Phase D — Harden.** Isolation tests as gate, E2E with the AI cross-check, SAP integration test on existing triggers, negative paths, UAT.

**Sequencing rationale:** everything except the adapters and the field spec is built before the external gates open. If security clearance slips two weeks, the loss is two weeks of *deployment*, not two weeks of *build*. The source document's own estimate is build ≈10% of elapsed time and approvals/testing/permissions ≈90% — this sequencing is the only thing that makes that survivable.

---

## 7. Inputs needed before Phase B

| # | Input | Blocks |
|---|---|---|
| 1 | ABI mapping Excel + BRD | Field spec, estimate |
| 2 | Attachment spec (types, cardinality, mandatory) | FR-04 config |
| 3 | Status enum | FR-07, AI team contract |
| 4 | Reference view column names / DDL | Adapter implementation |
| 5 | CPI contract (payload, auth, idempotency) | FR-10 — CT may already hold this from the prior SAP BTP work |
| 6 | Identity source for email→account | FR-01 |
| 7 | Workspace access + PrivateLink status | Deployment viability |

Items 1–5 are needed to build. Items 6–7 decide whether the architecture survives contact. See the questions document.
