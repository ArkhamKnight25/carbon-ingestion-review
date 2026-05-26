# MODEL.md — Data Model

## Core design principle

The data flows through three immutable/mutable layers:

```
IngestionBatch  →  RawRecord (immutable)  →  EmissionRecord (mutable until locked)
```

Auditors see the full chain: what file came in, what row it was, and what emission figure the analyst signed off on.

---

## Entity overview

### Tenant
Single enterprise client. Every table has a `tenant_id` FK. Multi-tenancy is shared-database, separate rows (not separate schemas or databases). Justification: simpler for a prototype; row-level isolation is enforced at the ORM layer on every query. Production would add Postgres RLS as a belt-and-suspenders layer.

### Facility
A physical site within a tenant. Electricity records link to a Facility for grid region lookup (Scope 2 emission factor selection). SAP records resolve plant codes to a Facility via `PlantCodeMapping`.

### PlantCodeMapping
SAP plant codes (e.g. `BHM1`) are meaningless without a lookup table. Each tenant provides this mapping at onboarding. In the prototype it is seeded; in production the client uploads a mapping CSV.

### EmissionFactor
Versioned lookup table for emission factors. Seeded from DEFRA 2023 GHG Conversion Factors. Each factor has `valid_from` / `valid_to` to support future year updates without corrupting historical records. Records point to the factor used at the time of ingestion.

### IngestionBatch
Source-of-truth anchor. One batch per file upload. Fields:
- `source_type`: SAP_FUEL | UTILITY_ELEC | TRAVEL
- `file_hash`: SHA-256 of the uploaded file. Prevents duplicate ingestion.
- `parse_errors`: JSON array of `{row, field, message}` entries for rows that failed to parse (not saved as EmissionRecords).
- `uploaded_by` + `uploaded_at`: who ran the ingestion.

### RawRecord
**Immutable.** One per source row that successfully parsed. Stores `raw_data` as a JSON dict with the original field names and values, exactly as they appeared in the file. This is what auditors use to verify the EmissionRecord was derived faithfully. Never updated after creation.

### EmissionRecord
**Mutable until locked.** Derived from a RawRecord. Key design decisions:

**Scope + category**: Stored explicitly. Category follows GHG Protocol Scope 3 categories where applicable (e.g. `scope3_cat6_flight` = Category 6, business travel).

**Activity period**: `activity_start` + `activity_end` stored as dates, not normalized to a calendar month. Utility billing periods rarely align with calendar months (a 29-day billing cycle starting Jan 3 runs into February). Forcing month normalization would introduce allocation assumptions not defensible to auditors.

**Dual quantity fields**:
- `quantity_raw` + `unit_raw`: exactly as parsed from source
- `quantity_normalized` + `unit_normalized`: converted to canonical units (litres for fuel, kWh for electricity, km for travel, room_nights for hotels)

Both are stored. Discarding the raw value loses the audit trail of what the source actually said.

**co2e_kg**: Computed at ingestion time as `quantity_normalized × emission_factor.factor`. Stored denormalized for query performance. Recomputable from normalized quantity + emission factor FK.

**extra**: JSONField for source-specific fields that don't fit the normalized schema:
- SAP: `movement_type`, `plant_code`, `material_number`, `vendor`
- Utility: `meter_id`, `tariff`, `demand_kw`, `billing_period_days`
- Travel: `origin_iata`, `destination_iata`, `cabin_class`, `distance_estimated`

### Status state machine

```
pending ──→ flagged ──→ approved ──→ locked  (terminal)
    │                      │
    └──────────────→ rejected ──→ pending  (analyst can re-open)
```

- `pending`: created by ingestion pipeline
- `flagged`: automatically set when validation rules fire
- `approved` / `rejected`: analyst action
- `locked`: batch lock action; requires all records to be approved or rejected first

Rejected records revert to pending rather than being deleted. This preserves the audit trail while allowing the analyst to correct an erroneous rejection.

### AuditEvent
Append-only log. One row per status change or edit on an EmissionRecord. Fields:
- `before_value` / `after_value`: JSON snapshots of what changed
- `actor`: the User who triggered the change (null for automated flagging)
- `timestamp`: when it happened

Never deleted. This table is what goes to auditors alongside locked records.

---

## Scope classification

| Source | Scope | Category |
|--------|-------|----------|
| SAP diesel/petrol | 1 | scope1_fuel_mobile |
| SAP natural gas / heating oil | 1 | scope1_fuel_stationary |
| Utility electricity | 2 | scope2_electricity |
| Travel - flights | 3 | scope3_cat6_flight |
| Travel - hotels | 3 | scope3_cat6_hotel |
| Travel - ground | 3 | scope3_cat6_ground |

Scope 3 Category 6 = Business Travel (GHG Protocol).

---

## What this model does not handle (see TRADEOFFS.md)

- Scope 3 Category 1 (purchased goods and services) from SAP procurement POs
- Market-based Scope 2 (requires REGOs / EACs per facility; only location-based implemented)
- Scope 3 Category 7 (employee commuting)
- Multi-currency cost tracking
- Organizational boundary settings (equity share vs operational control)
