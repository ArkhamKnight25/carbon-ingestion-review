# SOURCES.md

Notes on what I read while building each of the three ingest paths, why the sample data looks the way it does, and what would actually break the first time a real client's file showed up.

## 1. SAP fuel movements

The transaction sustainability teams care about is **MB51 — Material Documents List**, which reports goods movements posted in SAP's Materials Management module. A few things shaped the parser:

The export mechanism is the standard ALV grid "export to spreadsheet" button. That is the workflow a sustainability lead actually runs — log into SAP GUI, open MB51, filter by plant and date range, hit export, attach the file to an email. Nothing about it is an API call.

German column headers are the default in SAP installations in Germany, Austria, and Switzerland. The headers are documented in SAP's field catalog: `Buchungsdatum` (posting date), `Belegdatum` (document date), `Menge` (quantity), `Mengeneinheit` (unit of measure), `Werk` (plant), `Bewegungsart` (movement type), `Material`, `Materialkurztext` (material short text). The parser's alias dict maps every one of those to its English canonical name, and also accepts the English equivalents straight up for English-configured systems.

Movement types are 3-digit codes that classify a goods movement. The relevant ones for fuel consumption are 261 (goods issue to production order — by far the most common), 262 (reversal of 261), 201/202 (goods issue/return for cost centre), and 551/552 (scrapping). I include 281/282 as well because some clients post fuel against networks instead of production orders. Anything else is filtered out with a parse-error row so the analyst can see what was skipped — for example, type 101 is a goods receipt and means fuel arrived at the plant, not that it was burned.

Units are stored as SAP's internal codes — `L` for litres, `GAL` for gallons, `M3` or `CBM` for cubic metres, `KG` for LPG, `TO` for tonnes. The parser normalises to litres for liquid fuel and m³ for gas, applying conversions for the non-SI inputs. Date formats are typically dd.mm.yyyy in German installations and yyyy-mm-dd or dd/mm/yyyy elsewhere; the parser tries seven formats in order.

Plant codes are four-character alphanumeric strings unique within a client's SAP system. `BHM1` could be Birmingham Factory #1 or a name that means nothing without the client's lookup. The model has `PlantCodeMapping` for this and the SPA has a Settings page where an admin can edit the mapping.

Sources consulted: SAP Community threads on MB51 export behaviour (community.sap.com), the SAP field catalog documentation for MKPF (material document header) and MSEG (material document item), and a couple of public posts from sustainability consultants describing what their clients actually send them.

### Sample data — why it looks like that

`samples/sap_fuel_sample.csv` is shaped like a German-configured export. It has German headers, three plant codes (BHM1, MCR1, LDN1) that map to seeded facilities, two materials (D000100 Diesel HVO B7 and G000200 Erdgas), mostly movement type 261. A few rows are intentional edge cases:

- One row with a negative quantity (-200 L). SAP sometimes posts fuel returns as a negative 261 instead of a 262 reversal; the parser takes the absolute value and tags the record with `negative_quantity_taken_as_return` for analyst review.
- One large quantity (99,999 L in a single posting) that trips the 3-sigma outlier flag.
- One row with movement type 101 (goods receipt) that should not be ingested — surfaces in `parse_errors` instead of becoming a record.
- One row with an unknown plant code (UNK9) — ingests but is flagged `missing_facility`.
- One row with an unknown material (XYZ9999) — fails parsing and surfaces in `parse_errors`.
- Natural gas rows in m³ to exercise the unit-normalisation path.

### What would break on a real deployment

- Plant-code resolution at scale. The prototype seeds three; a real client comes with dozens. We need an onboarding step that takes the client's plant-code → facility CSV.
- Movement-type tuning. Production clients post movements for hundreds of materials (packaging, raw materials, consumables) and the filter would need to be tightened per client based on which materials are actually fuel.
- Multiple SAP systems. Large enterprises often have several SAP instances by region or acquisition, with different plant codes and unit configurations. Per-system ingestion config would be needed.
- Decimal separator. European systems use `1.234,56` and US ones use `1,234.56`; the parser handles both heuristically but explicit locale detection would be safer.
- Encoding. SAP exports come out in UTF-8, UTF-8 with BOM, Latin-1, or cp1252 depending on configuration. The parser tries the encodings in order; in practice this is rarely a problem but not never.

## 2. Utility electricity

Utility portal CSV exports vary by provider but share a common skeleton.

I looked at ComEd in the US (their "View Account Usage Data" portal gives billing-period start/end, days, total kWh, on-peak/off-peak kWh, billing demand in kW, and rate code); EDF, E.ON, and British Gas in the UK for smart-meter exports (broadly similar but UK large commercial accounts get half-hourly interval data, which would need aggregation before ingestion); and the Green Button / ESPI XML standard, which is a US DOE initiative supported by some US utilities and almost no UK or European ones. CSV is the safest primary path.

The shape of the data taught me one thing: billing periods are the unit of utility data, not calendar months. A bill dated February 15th may cover January 18th to February 16th — 30 days that span two months. ESG platforms that force this into "February" make an allocation assumption that is not in the source data. The model stores actual `activity_start` and `activity_end` so the downstream allocation choice is explicit.

### Sample data — why it looks like that

`samples/utility_electricity_sample.csv` uses ComEd-style column names. It includes:

- Three facilities (Birmingham Factory, Manchester Warehouse, London HQ) with different account numbers.
- Billing periods starting January 3rd, not January 1st — utility cycles do not reset on the first of the month.
- Variable billing period lengths (29, 30, 31, 32 days) — real cycles drift.
- Multiple meters at Birmingham Factory (MTR-BHM-001, 002, 003) — multi-meter sites are normal.
- One zero-kWh row for London HQ in March. Real meter reads of zero usually mean either a read failure or a vacant facility (refurbishment, between tenants). The parser flags it `zero_value`.
- Peak/off-peak kWh split — ComEd's TOU rates expose this; the prototype stores it in `extra` but uses the total kWh for the emissions calculation.
- Demand (kW) and tariff code — included because real exports have them; kept in `extra` for future market-based work.

### What would break on a real deployment

- Half-hourly interval data. UK large-commercial accounts get HH data, not billing summaries. We would need an aggregation step before creating emission records.
- Estimated reads. Real CSVs often include an Estimated/Actual flag per reading. Estimated reads should auto-flag.
- Dual-fuel bills. Some accounts have gas and electricity on the same export. The current parser assumes electricity only.
- Negative kWh from solar/CHP net export. The bug-fix here: zero kWh is a `zero_value` flag (probable error), but negative kWh is a separate `negative_export` flag (legitimate generation back to the grid).
- Demand and capacity charges. Bills include kW demand, capacity charges, and network charges that are not kWh consumption. A naive parser could double-count if it grabbed the wrong column.

## 3. Corporate travel

Travel data comes out of Travel Management Companies (TMCs), and I looked at two specifically.

Navan (formerly TripActions) is a large TMC with a reporting export that produces one CSV row per booking segment. Flight rows carry origin/destination airports, cabin class, and sometimes distance. Hotel rows carry check-in/check-out dates and a city. Ground rows carry mode (taxi, rail, car) and sometimes distance. The trip-type segmentation maps cleanly onto our three emission categories.

Concur Travel & Expense is more complex. Its travel module exports a similar shape, but the expense module mixes in non-travel categories (meals, supplies) that would need filtering. Concur also has a v4 OAuth REST API; it works but it needs enterprise credentials and is not a realistic ingestion path for a sustainability lead.

For distances, the IATA airport-code standard is universal — three-letter codes (LHR, JFK, DXB, SIN) identify every commercial airport. When the TMC ships airport codes but no distance, Haversine on the airport coordinates gives an estimated great-circle distance. The public dataset at `github.com/datasets/airport-codes` has roughly 9,000 entries; the prototype bakes in about 36 of the major ones to keep the dependency footprint small.

Emission factors come from DEFRA 2023 GHG Conversion Factors for Company Reporting. DEFRA's flight factors already include a 1.891x radiative-forcing uplift to account for the non-CO2 climate effects of aviation (contrails, NOx, water vapour at altitude), so I do not apply an additional uplift on top.

### Sample data — why it looks like that

`samples/travel_sample.csv` is shaped like a Navan export.

- One employee (EMP-0042) with a complete LHR ↔ JFK round trip — outbound flight, 3-night hotel in New York, two taxi legs, return flight. Touches all three trip_type branches in one trip.
- A business-class flight (EMP-0117 LHR → DXB) to exercise the business-class emission factor, which is roughly 3x economy.
- A multi-leg trip (EMP-0089 LHR → SIN → BOM → LHR) with one segment that explicitly carries `distance_km` (10,841 km for LHR → SIN) and the others left blank so Haversine fills them in. Demonstrates both paths.
- A premium-economy segment to hit that factor.
- Rail (Manchester, 212 km, two ways) to exercise the rail factor.
- A flight to an unrecognised IATA code (`ZZZ`) — fails parsing and surfaces in `parse_errors` rather than computing a garbage number.
- A ground-transport row with no distance and no airport pair — surfaces in `parse_errors` because there is no defensible way to compute emissions.

### What would break on a real deployment

- Haversine under-counts by 5-10% relative to actual routed flight distance. DEFRA's factor compensates partially via the radiative-forcing uplift. I would still want to document the limitation per client.
- The airport-code dictionary is incomplete. A real deployment would load the full ~9,000-entry IATA dataset into a database table.
- Hotel emission factors are a global average (20.8 kgCO2e/room-night). The variance is large — a hotel in India on a coal-heavy grid emits much more than one in Norway on hydro. Country-level factors are a known v2 item.
- Personal travel mixed in. Corporate travel platforms capture personal trips booked on the corporate card. Without a `business_purpose` flag and filtering, those inflate Scope 3 Category 6.
- Rail distances should be routed distances, not straight lines, but most TMCs do not provide them and Haversine is a poor substitute over land.
- Currency normalisation is not implemented. Travel cost data uses many currencies. Not needed for emissions math, but useful for downstream cost-per-tonne analysis.
