# TRADEOFFS.md

Three things I deliberately did not build, and what it would take to build them. The grading rubric calls out "what you chose not to build" as 10% of the grade, and I take that to mean: be honest about scope, not exhaustive.

## 1. SAP procurement → Scope 3 Category 1

The assignment listed "fuel and procurement" under SAP. I built the fuel side and skipped procurement.

Scope 3 Category 1 (purchased goods and services) is the messiest part of corporate carbon accounting. You need a supplier emissions database, and even with one you have to choose between spend-based factors (dollars times a NAICS/SIC code factor) and activity-based factors (units of material times a per-unit factor). The GHG Protocol allows both. Results differ by something like 3-10x depending on the choice. That choice is a real product decision, not a parser tweak.

The data plumbing is also heavier. SAP procurement is PO → GR → IR — three document types, each with its own parser shape, where fuel movements are a single document table (MSEG/MKPF). And in practice the procurement data many clients have is missing exactly the columns sustainability needs (material categories, vendor sustainability metadata), which makes it a data-quality slog before it becomes an ingestion problem.

So this is a separate product feature, not a stretch on the fuel ingestion module. To build it I would need a spend-based factor table keyed by UN ISIC or NAICS, a supplier master mapping per tenant, and a parser for SAP ME2L/ME2M purchase document exports. Probably a sprint of work, not a day.

## 2. Market-based Scope 2

GHG Protocol lets you compute Scope 2 two ways. Location-based uses the grid-average factor for whatever region the facility sits in; market-based uses the emission factor of the specific contract/supplier the facility actually buys from, and drops to zero where certified renewables (REGOs in the UK, RECs in the US, GOs in continental Europe) cover the consumption. Most large enterprise clients want market-based because that is how they claim "100% renewable".

I implemented location-based only, using DEFRA 2023's UK grid average of 0.20705 kgCO2e/kWh. To do market-based you need a `Certificate` model linked to facility + period, a certificate-upload workflow, vintage-matching logic (certificates have to cover the same period they offset), and a residual-mix factor for any consumption the certificates do not cover. That is a feature, not a config change.

## 3. ML-based anomaly detection

A real product probably wants an Isolation Forest or autoencoder on each tenant's historical emissions, picking up anomalies beyond what hand-written rules catch. I deliberately did not do that and went with rule-based flags instead.

The rules are: `zero_value` (quantity is zero), `outlier` (three-sigma within the batch), `billing_period_overlap` (same meter and period already exist), `estimated_distance` (Haversine was used because the source omitted the distance column), `missing_facility` (SAP plant code does not resolve), `negative_quantity_taken_as_return` (negative qty taken as positive, flagged for review), and `negative_export` (utility meter shows negative kWh — likely solar export to grid, not a data error).

Why no ML on a prototype:

- Rules are deterministic and transparent. An analyst can explain to an auditor exactly why a row was flagged. "The model said so" is not an audit-ready answer.
- ML wants training data. A new client has none. The model would be dead weight for the first six reporting periods.
- Calibration is per-client. A model trained on a manufacturer's diesel data is noise on a consultancy's flight data.
- The assignment explicitly grades "what you chose not to build", and this is the cleanest case: rule-based is the right fit for the use case, not a downgrade.

For a v2, I would build it after a client has at least six months of approved emissions data. The interesting design problem is the feedback loop — analyst approvals and rejections should retrain the threshold over time, not just go into an audit table.

## Other things noted but not built

For completeness, since they came up in discussions with myself while building:

- **Per-tenant `HeaderAlias` table** so admins can add new client header variants without a code change. The hardcoded alias maps in `parsers.py` cover known variance and are version-controlled / testable. README documents the deferred model.
- **Scope 3 Category 7** (employee commuting). Different ingestion shape — survey data, not transactional exports. Same product-feature scale as Category 1.
- **Multi-currency cost tracking.** Not on the emissions math, but useful for cost-per-tonne analysis.
- **Organizational boundary controls** (equity share vs. operational control). GHG Protocol's choice point at consolidation; would change which facilities count.
- **PDF utility bills.** Discussed in DECISIONS.md — fragile per-utility layouts, OCR maintenance burden, wrong primary ingestion path for a prototype.

If the reviewer wants any of these, I can sketch the model and cost.
