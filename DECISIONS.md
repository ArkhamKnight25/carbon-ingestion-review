# DECISIONS.md

A running log of the ambiguities the assignment left open and how I resolved them. For each source I picked one ingestion mode and a subset of the messy real world to handle; the rest is documented as known omissions in TRADEOFFS.md.

## SAP

I went with the flat MB51-style CSV export rather than IDoc, OData, or BAPI. The reasoning is mostly about who actually generates the file. Sustainability teams do not have programmatic SAP access. They open MB51 (the Material Documents List), filter by plant and date, and hit "export to spreadsheet" from the standard ALV grid. That CSV is what lands in their email. IDoc is a system-to-system EDI format and no sustainability lead ever forwards one of those. OData needs a licensed Fiori Gateway plus OAuth, which a prototype cannot assume, and BAPI is direct RFC, which is not a web-app concern. So the realistic shape is a CSV that came out of MB51, and that is what the parser handles.

The assignment scope was "fuel and procurement", but I deliberately built fuel only. Fuel is Scope 1, the math is litres times an emission factor, and the data quality bar is reachable. Procurement maps to Scope 3 Category 1, which needs a supplier emissions database, a spend-based vs. activity-based factor choice with a 3-10x outcome spread, and a different parser shape entirely (PO → GR → IR). It is a separate product feature, not an extension of fuel ingestion. TRADEOFFS.md #1 walks through this.

For movement types I accept the codes that mean "fuel left inventory and was consumed": 261 and 262 for goods issue/return to production orders, 201/202 for cost-centre issues, 551/552 for scrapping. Movement types that mean "fuel arrived" (101) or "fuel moved" (311) are excluded with a parse-error row so the analyst can see what was skipped and why.

German column headers are normal in DE/AT/CH installations, so the parser aliases `Buchungsdatum` → `posting_date`, `Menge` → `quantity`, `Werk` → `plant`, and so on. The full alias table is in `backend/ingestion/parsers.py`. Unmapped headers fall through with their original name lowercased rather than dropped, so nothing disappears silently.

Things I would push back to the PM:

- Do clients maintain a plant-code → facility mapping themselves, or do we own the onboarding for it? Right now I seed the demo mapping and the analyst can edit it from a Settings page, but a real client would deliver dozens of plant codes on day one.
- Are there installations where fuel is tracked in energy units (GJ, MWh) instead of litres or cubic metres? The unit normalizer handles L/GAL/M3/CBM/KG today; energy units would need a different conversion path.
- Should goods receipts (101) feed inventory-based consumption instead of relying on direct goods issues? Some clients prefer the inventory diff method.

## Utility electricity

The realistic format here is the portal CSV. PDF bills look tempting until you try to parse them: every utility ships a different layout, and even within a single utility the layout drifts between billing periods. A PDF pipeline either needs a custom parser per utility or a paid OCR service, and the maintenance load is awful. The Green Button (ESPI) XML standard is a US Department of Energy thing that some American utilities support and most non-US ones do not, so it is not a primary path for an international client base. Portal CSVs are what facilities teams actually download; ComEd, EDF, E.ON, and the UK suppliers all have a "download usage data" button that produces broadly similar files. Field names vary, so the parser uses a flexible header-alias map.

Billing periods are stored as the source reports them. A 29-day cycle starting January 3rd is just that, not "January". Squeezing it into a calendar month requires an allocation decision (do the two February days carry over? are they prorated?), and different analysts pick different conventions. I would rather keep the source dates intact and let the analyst and auditor allocate consciously. The `activity_start`/`activity_end` on every emission record mirrors the actual billing window.

Multi-meter support matters because real facilities are not single-meter sites. A factory might have a main supply meter, an HVAC sub-meter, and a lighting sub-meter. The parser keeps each row as its own emission record and tags the source meter in the `extra` JSON column. No aggregation happens at ingest time.

Things I would push back to the PM:

- Market-based Scope 2 (REGO/REC/GO certificates per period) is a fairly big add. Right now I only do location-based with DEFRA's UK grid factor. Worth scoping for v2.
- Some CSVs include an estimated/actual flag per reading. Should estimated reads auto-flag for review? I lean yes, but it is an opinion.

## Corporate travel

I modeled on Navan's reporting export. Navan (formerly TripActions) is a large TMC and its CSV format separates flights, hotels, and ground transport cleanly into `trip_type` rows. That maps onto our three emission factor categories without a translation layer. Concur's expense export overlaps but mixes in non-travel expense categories that would need filtering. The OAuth API path (Concur v4) needs enterprise credentials I cannot reasonably ask the reviewer to provide, so the realistic surface is still a CSV.

Distance is the hard part. The parser tries three paths in order. If the row has `distance_km`, I trust the TMC's number. If it does not but both IATA codes are present, I compute the great-circle distance via Haversine and flag the record `estimated_distance` so the analyst knows. If neither is available I refuse to compute a number and create a parse error instead, because the alternative is a silently wrong CO2e.

Great-circle distance under-counts because real flights follow airways and are 5-10% longer than the straight-line. DEFRA's per-km factors already bake in a 1.891x radiative-forcing uplift, which partially compensates. SOURCES.md is honest about this limitation.

Cabin classes map to DEFRA 2023 long-haul economy/premium/business/first factors. If the source says `business` I pick the business factor, if it says `Y` or `coach` it lands on economy, and if the value is unrecognised I default to economy and flag. The fare-code map (`Y`, `M`, `J`, `F`, etc.) is there because Concur often ships single-letter fare classes instead of full names.

Hotels use DEFRA's global average of 20.8 kgCO2e per room-night. A real platform would split this by country because a Mumbai hotel running on coal-heavy grid power emits more than a Norwegian one on hydro. SOURCES.md notes this as a known limitation.

Things I would push back to the PM:

- Per-country hotel factors, or is the global average acceptable for year one?
- TMC exports often include personal travel booked on a corporate account. Should we filter by business-purpose code or treat that as the analyst's job?

## Data model

I went with shared-database multi-tenancy. Every table has a `tenant_id` FK and every query filters on it at the ORM layer. Separate schemas per tenant would force schema-routing logic and per-tenant migrations, which is real production engineering and not something a four-day prototype needs. A production hardening pass would add Postgres Row-Level Security on top of the ORM-level filter, but the data isolation contract is already in place.

Rejected records stay in the database with `status='rejected'` rather than being deleted. Auditors care that a row arrived, was reviewed, and was deemed invalid; that is a different statement from "the row never existed". Deletion would discard exactly the trail an audit wants.

Source-specific fields go in a JSONField called `extra`. Meter IDs, movement types, IATA codes, cabin classes, tariff codes; none of these belong on the normalized schema because most rows would have to leave most columns null. JSONField means each source carries its own context without bloating the table. Querying these fields is slower than a normalized column, but the access pattern is "show me the source data for this record I am reviewing", not analytics over millions of rows, so it is the right trade.

## Deployment

Live on Render. The backend is a free Python web service running gunicorn against a Neon Postgres instance, and the frontend is a free Render static site that consumes the API over CORS. The Render free tier sleeps services after 15 minutes of idle, so the first request after a quiet period takes ~30-60 seconds; the frontend pings `/api/health/` every ten minutes from any open tab to keep the backend warm during a review session.

I started on Railway and switched because Render's free Postgres limit forced an external DB (Neon) anyway, and at that point Render's Blueprint flow gave the cleanest single-file deploy. `render.yaml` at the repo root provisions both services; `DATABASE_URL` is a `sync: false` env var so the Neon connection string is not committed to git.
