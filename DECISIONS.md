# DECISIONS.md — Every ambiguity resolved

## SAP

**Format chosen: MB51-style flat CSV (not IDoc, not OData, not BAPI)**

SAP offers four export mechanisms. I chose flat CSV because:
- Sustainability teams do not have programmatic SAP access; they run MB51 (Material Documents List) and export to Excel/CSV via the standard ALV grid export. This is the actual workflow at most enterprise clients.
- IDoc is a message-based EDI format used for system-to-system integration; no sustainability team hands these to an ESG platform.
- OData would require a licensed SAP Fiori Gateway and OAuth credentials; unrealistic for a prototype and uncommon in sustainability reporting contexts.
- BAPI requires direct RFC connectivity; outside scope for a web-based ingestion tool.

**Scope: fuel movements only (not procurement POs)**

The assignment says "fuel and procurement." I chose fuel only because:
- Fuel = Scope 1 (direct emissions). Straightforward: litres × emission factor.
- Procurement from SAP = Scope 3 Category 1 (purchased goods and services). This requires spend-based or activity-based emission factors per material/vendor category, a supplier emissions database, and significant data quality assumptions. This is a separate product feature, not an extension of fuel ingestion.
- I document this omission explicitly in TRADEOFFS.md.

**Movement types: 261/262 (goods issue/return), 201/202, 551/552**

Movement type 261 = goods issue to production order (most common fuel consumption posting). 262 = reversal. 201/202 = goods issue/return for cost center. 551/552 = scrapping. All indicate fuel leaving inventory for consumption. Movement types like 101 (goods receipt) or 311 (stock transfer) are excluded — they represent fuel arriving or moving, not being consumed.

**German headers: mapped to English**

SAP installations in Germany, Austria, Switzerland ship German column headers by default. The parser maps `Buchungsdatum` → `posting_date`, `Menge` → `quantity`, etc. Any unmapped header falls through with its original name lowercased.

**What I'd ask the PM:**
- Do clients have a standard plant code → facility mapping they maintain, or should we build a UI for it?
- Are there SAP instances where fuel is tracked in energy units (GJ, MWh) rather than volume? Our sample uses litres and cubic metres.
- Should we handle goods receipts (incoming fuel) to compute inventory-based consumption rather than direct goods issues?

---

## Utility electricity

**Format chosen: portal CSV export (not PDF, not Green Button API)**

- PDF parsing: structurally fragile. Every utility has a different bill layout. Even within one utility, layouts change between billing periods. PDF → structured data requires either a custom parser per utility or a paid OCR service. Not appropriate for a prototype and high maintenance in production.
- Green Button / ESPI API: a US standard (OpenESB) supported by some but not all utilities. UK and European utilities generally do not support it. Not universal enough to build as the primary ingestion path.
- Portal CSV: what facilities teams actually download. ComEd, EDF, E.ON, and most large utilities offer a "download usage data" CSV export from their account portal. The fields are consistent enough to normalize with flexible header matching.

**Billing periods: stored as-is**

A utility billing period might be Jan 3 → Feb 1 (29 days). Forcing this into "January" requires a decision about how to allocate the 2 days of February. Different analysts make different choices. I store `billing_period_start` + `billing_period_end` and let the analyst and auditor decide on temporal allocation. The emission record's `activity_start`/`activity_end` reflects the actual billing period.

**Multi-meter support**

Real facilities have multiple meters (sub-meters per floor, separate meters for HVAC, lighting, production). The `meter_id` field in `extra` identifies which meter a record came from. Multiple meters in one upload are supported; records are created per row, not aggregated.

**What I'd ask the PM:**
- Do clients want market-based Scope 2 (requires REGO/EAC certificates per period)? Currently only location-based is implemented.
- What happens when a meter reading is estimated rather than actual? Some utility CSVs include an "E/A" flag. Should estimated reads be auto-flagged?

---

## Corporate travel

**Platform: Navan-style CSV export**

Navan (formerly TripActions) is a major corporate travel management platform. Their reporting export produces a CSV with one row per booking segment. Concur's expense export has a similar structure but includes more expense categories beyond travel. I modeled on Navan's travel report format because it cleanly separates flights, hotels, and ground transport into `trip_type` rows, which maps directly to different emission factor categories.

**Distance calculation**

Priority order:
1. Use provided `distance_km` if present (trust the platform's routing data)
2. If `origin_iata` + `destination_iata` present: compute Haversine great-circle distance, flag `estimated_distance = true`
3. If neither: flag for analyst review, do not create an EmissionRecord

Haversine gives great-circle distance, not actual routed flight distance. Real flights follow airways and are typically 5–10% longer than great-circle. Production would apply a standard uplift factor (DEFRA recommends a radiative forcing uplift of 1.891× the distance-based CO2 figure, which partially compensates). I document this limitation in SOURCES.md.

**Cabin class**

Maps to DEFRA 2023 emission factors:
- Economy: 0.1530 kgCO2e/km/pax
- Premium economy: 0.2297 kgCO2e/km/pax
- Business: 0.4294 kgCO2e/km/pax
- First: 0.5714 kgCO2e/km/pax

Default to economy if not specified; flag if the value is unrecognized.

**Hotel emission factor**

DEFRA 2023 average: 20.8 kgCO2e per room-night. In production, this should be broken out by country/region (hotels in high-carbon-intensity grids emit more). I use the global average and note this in SOURCES.md.

**What I'd ask the PM:**
- Should we support per-country hotel emission factors, or is the global average acceptable for year 1?
- Navan/Concur exports often include personal travel booked on the corporate platform. Should we filter by business purpose code, or is that the analyst's job?

---

## Data model

**Shared-DB multi-tenancy (not separate schemas)**

Separate schemas would require dynamic schema routing and migration management per tenant. For a prototype with one tenant this is unnecessary overhead. `tenant_id` on every table, enforced at the ORM layer, is simpler and auditable.

**`rejected` status separate from deletion**

A rejected record remains in the database with status=rejected. This preserves the audit trail: auditors need to know that certain rows arrived, were reviewed, and were determined to be invalid — not that rows simply never existed.

**JSONField for `extra`**

Source-specific fields (meter_id, movement_type, origin_iata) don't belong in the normalized schema — they'd require nullable columns for every field on every row regardless of source type. JSONField lets each source store its relevant context without bloating the table. Querying these fields is less efficient than normalized columns, but for audit/review purposes (not analytics), this is acceptable.

---

## Deployment

**Railway over Render/Fly**

Railway provides Django + Postgres as a single project with one environment variable for DATABASE_URL. No custom Dockerfile required. Render requires more configuration for static files. Fly.io requires Docker knowledge. Railway was fastest to a working deployment.
