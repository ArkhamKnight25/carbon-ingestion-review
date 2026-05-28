# MODEL.md

The data model has one job: make every emission figure traceable back to the exact row of the exact file that produced it, and keep a record of every human decision in between. The shape that fell out of that is three layers — a batch, an immutable raw row, and a mutable emission record — wired through a status state machine, with an append-only audit log on the side.

```
IngestionBatch  →  RawRecord (immutable)  →  EmissionRecord (mutable until locked)
                                                     │
                                                     └── AuditEvent (append-only)
```

When an auditor asks "where did this number come from", they get back: the file we received, the line in that file we parsed, the emission factor we applied, every change an analyst made, and who made each change.

## Entities

**Tenant.** The enterprise client. Every other table has a `tenant_id` foreign key and every query in the API filters on it. Multi-tenancy is shared-database, separate rows. Schema-per-tenant would force dynamic routing and per-tenant migrations, which I do not think a prototype should be doing. In production I would layer Postgres Row-Level Security on top as a belt-and-suspenders thing, but the isolation contract already lives at the ORM layer.

**Facility.** A physical site under a tenant. Electricity records resolve to a facility for grid-region lookup (Scope 2 factor selection), and SAP plant codes resolve to a facility through `PlantCodeMapping`.

**PlantCodeMapping.** SAP plant codes like `BHM1` are opaque without a lookup. Each tenant provides their own mapping. Seeded in the prototype with three sites, and there is a Settings page in the SPA so an admin can edit the table without touching Django admin.

**EmissionFactor.** Versioned lookup of emission factors, seeded from the DEFRA 2023 GHG Conversion Factors. Each row has `valid_from`/`valid_to` so future-year updates do not corrupt historical records — a 2024 deployment can ingest 2023 data with 2023 factors and 2024 data with 2024 factors side by side. Every `EmissionRecord` points at the exact factor row it used at ingest time.

**IngestionBatch.** One row per file upload. This is the source-of-truth anchor. Fields:

- `source_type` (`SAP_FUEL` | `UTILITY_ELEC` | `TRAVEL`) drives parser dispatch.
- `file_hash`: SHA-256 of the uploaded bytes; uniqueness against tenant prevents the same file being ingested twice.
- `parse_errors`: a JSON array of `{row, field, message}` entries for rows that failed to parse. These rows do not become `EmissionRecord`s but they are visible to the analyst on the upload result screen, so nothing fails silently.
- `uploaded_by` + `uploaded_at`: provenance.

**RawRecord.** One per successfully parsed source row, stored as a JSON dict that mirrors the original headers and values from the file. Immutable — never updated after creation. This is what the auditor compares against when they want to verify the emission record was derived faithfully.

**EmissionRecord.** Mutable until the batch is locked. Carries scope (1/2/3), a category string that follows the GHG Protocol categories where it can (e.g. `scope3_cat6_flight` is Category 6 — business travel), and two pairs of quantity fields. `quantity_raw` / `unit_raw` is what the source said. `quantity_normalized` / `unit_normalized` is what we converted it to — litres for fuel, kWh for electricity, kilometres for travel, room-nights for hotels. Both are kept; throwing away the raw value would mean losing the answer to "what did the source actually say".

`co2e_kg` is computed at ingest as `quantity_normalized × emission_factor.factor` and stored denormalized for query performance. It is also recomputable on the fly from the foreign key to the factor, so there is no risk of drift after a factor table update.

`activity_start` and `activity_end` are dates, not a calendar month. Utility billing periods rarely line up with calendar months — a 29-day cycle from January 3rd to February 1st should not be silently called "January". Storing the actual period lets the analyst decide on temporal allocation later if they need to.

`extra` is a JSONField for fields that only make sense to one source. SAP rows carry their movement type, plant code, material number, and vendor. Utility rows carry meter id, tariff, demand_kw, peak/off-peak split, days in period. Travel rows carry employee id, IATA codes, cabin class, and an `distance_estimated` flag. These do not belong on the normalized columns because they would be null for two-thirds of the records.

`status` is a state machine:

```
pending  ──→  flagged  ──→  approved  ──→  locked  (terminal)
   │                            │
   └──────────────→ rejected ───┘
```

`pending` is the default coming out of the ingest pipeline. `flagged` is set automatically when a validation rule fires (zero kWh on a utility meter, missing facility for an SAP plant, Haversine-estimated distance on a flight, three-sigma outlier within the batch). The analyst can move records into `approved` or `rejected`. `locked` is reached only by the batch-lock action, which refuses to lock if any record in the batch is still pending or flagged. A rejected record is not deleted; it stays in the database with `status='rejected'` because auditors care about rows that arrived and were thrown out, not just rows that never existed.

**AuditEvent.** Append-only. One row per status change, edit, automated flag, or batch lock. Carries `before_value` and `after_value` JSON snapshots, the user who triggered the action (null for automated events), a free-text note, and a timestamp. Never deleted. This table is what gets shipped to auditors alongside the locked records.

## Scope classification

| Source | Scope | Category |
|---|---|---|
| SAP diesel and petrol | 1 | `scope1_fuel_mobile` |
| SAP natural gas and heating oil | 1 | `scope1_fuel_stationary` |
| Utility electricity | 2 | `scope2_electricity` |
| Travel — flights | 3 | `scope3_cat6_flight` |
| Travel — hotels | 3 | `scope3_cat6_hotel` |
| Travel — ground | 3 | `scope3_cat6_ground` |

Scope 3 Category 6 is "Business Travel" in the GHG Protocol Corporate Value Chain Standard.

## Things this model deliberately does not handle

These are documented in TRADEOFFS.md with reasoning, but for completeness:

- Scope 3 Category 1 (purchased goods and services) from SAP procurement
- Market-based Scope 2 (REGOs / RECs / GOs per facility per period)
- Scope 3 Category 7 (employee commuting)
- Multi-currency cost tracking
- Organisational boundary settings (equity share vs. operational control)

If the reviewer wants any of these in scope I have rough sketches of what each would cost; none of them is a small addition.
