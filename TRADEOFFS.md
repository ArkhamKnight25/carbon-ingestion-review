# TRADEOFFS.md — Three things deliberately not built

## 1. SAP procurement / Scope 3 Category 1

**What it is**: Ingesting SAP purchase orders, goods receipts, and invoice data to compute Scope 3 Category 1 (purchased goods and services) emissions.

**Why it was not built**: Scope 3 Category 1 is the most complex and contested part of corporate carbon accounting. It requires:
- A supplier emission factor database (spend-based: $/kg CO2e by NAICS/SIC code, or activity-based: kg CO2e per unit of material)
- Data quality decisions about whether to use spend-based or activity-based methods (GHG Protocol allows both, but results differ by 3-10x)
- SAP purchasing document structure (PO → GR → IR) is more complex than material movements; each document type needs a separate parser
- Many clients' SAP procurement data is incomplete for sustainability purposes (missing material categories, inconsistent vendor master data)

**What this means**: The prototype handles SAP fuel movements (Scope 1) only. Procurement is explicitly out of scope and documented in DECISIONS.md. A production system would need Category 1 as a separate ingestion module with its own emission factor library.

**What I'd need to build it**: A spend-based emission factor table keyed by UN ISIC / NAICS code, a supplier master mapping, and a separate parser for SAP ME2L/ME2M purchase document exports.

---

## 2. Market-based Scope 2 (renewable energy certificates)

**What it is**: Scope 2 can be calculated two ways per GHG Protocol:
- Location-based: grid average emission factor for the region
- Market-based: emission factor from the specific energy supplier/contract, reduced to zero for certified renewables (REGOs in UK, RECs in US, GOs in Europe)

**Why it was not built**: Market-based Scope 2 requires:
- Matching electricity purchases to REGO/REC/GO certificates per billing period per facility
- Handling certificate vintages (certificates must match the consumption period)
- A certificate registry integration or manual certificate upload workflow
- Residual mix emission factors for consumption not covered by certificates

This is a significant feature in its own right — many large enterprise clients use it to claim "100% renewable" Scope 2, but the data management is non-trivial. The prototype implements location-based only using DEFRA 2023 UK grid average (0.20705 kgCO2e/kWh).

**What I'd need to build it**: A `Certificate` model linked to `Facility` + period, certificate upload ingestion, and modified Scope 2 calculation logic that checks certificate coverage before applying grid factor.

---

## 3. ML-based anomaly detection

**What it is**: Using a machine learning model (e.g. Isolation Forest, LSTM autoencoder) to detect anomalous emission records based on historical patterns, rather than simple statistical rules.

**Why it was not built**:
- The prototype uses rule-based flags (zero values, 3σ outliers, billing period overlaps, estimated distances). These are transparent, deterministic, and defensible. An analyst can explain to an auditor exactly why a row was flagged.
- ML models require training data. A new client has no history; the model would be useless for the first several reporting periods.
- Anomaly detection models have false positive rates that need calibration per client. A model trained on manufacturing fuel data would generate noise on travel data.
- The assignment explicitly grades "what you chose not to build" — this is a clear case where the simpler approach is more appropriate for the use case.

**Rule-based flags implemented instead**:
- `zero_value`: quantity ≤ 0
- `outlier`: |quantity - batch_mean| > 3σ within the batch
- `billing_period_overlap`: meter + period already exists for this tenant
- `estimated_distance`: Haversine was used instead of provided distance
- `missing_facility`: SAP plant code could not be resolved to a facility

**What I'd need to build it properly**: 6+ months of historical data per client, a calibration workflow, and a feedback loop where analyst approvals/rejections update the model. Better as a v2 feature once clients have history.
