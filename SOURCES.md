# SOURCES.md — What I researched for each source

## 1. SAP fuel movements

### What I researched

SAP's primary transaction for material document reporting is **MB51** (Material Documents List). It reports goods movements posted in Materials Management (MM). Key findings:

- **Export mechanism**: SAP's ALV (ABAP List Viewer) grid allows export to spreadsheet/CSV via the standard toolbar. This is the actual workflow for sustainability teams — they run MB51, filter by plant and date range, and export. No API access required.
- **German headers**: Default SAP installations in German-speaking countries use German column names. `Buchungsdatum` (posting date), `Menge` (quantity), `Mengeneinheit` (unit of measure), `Werk` (plant), `Bewegungsart` (movement type). These are documented in SAP's standard field catalog.
- **Movement types**: SAP uses numeric movement types to classify goods movements. Type 261 = goods issue to production order (primary consumption). 262 = reversal of 261. 201/202 = goods issue/return for cost center. A real dataset will contain dozens of movement types; the parser filters to fuel-relevant ones only.
- **Units**: SAP stores quantities in the base unit of measure configured per material. Common fuel units: L (litres), GAL (gallons), M3 (cubic metres), KG (kilograms for LPG). The unit column contains SAP's internal unit code, which may differ from ISO units.
- **Plant codes**: 4-character alphanumeric codes unique within a client's SAP system. `BHM1` might mean "Birmingham Factory #1" or might be meaningless without a client-provided mapping table.
- **Dates**: Two date fields common in MB51: `Buchungsdatum` (posting date = when the goods movement was entered in SAP) and `Belegdatum` (document date = date on the physical delivery note). For emissions reporting, posting date is used.

**Source consulted**: SAP Community forums on MB51 exports (community.sap.com), SAP field documentation for MKPF (material document header) and MSEG (material document item) tables.

### Sample data rationale

The sample file (`sap_fuel_sample.csv`) includes:
- German column headers (realistic for a German-configured SAP system)
- Three plants: BHM1, MCR1, LDN1 (mapped to Birmingham Factory, Manchester Warehouse, London HQ)
- Two materials: D000100 (Diesel HVO) and G000200 (Erdgas = natural gas)
- Movement type 261 throughout (goods issue for consumption)
- One negative quantity row (row 8: -200L) — SAP sometimes posts fuel returns as negative goods issues rather than movement type 262. The parser takes absolute value and notes it.
- One outlier row (row 11: 99,999L in one posting) — triggers the outlier flag
- Cubic metres for natural gas (realistic — gas is metered in m³ in Europe)

### What would break in real deployment

1. **Plant code resolution**: The prototype seeds three plant codes. A real client would have dozens. An onboarding workflow to upload the plant-code mapping CSV is needed.
2. **More movement types**: Production clients have material movements for dozens of non-fuel materials (packaging, raw materials, consumables). The movement type filter would need tuning per client based on which materials represent fuel.
3. **Multiple SAP systems**: Large enterprises may have 3–10 SAP systems (by region, by acquisition). Each may have different plant codes, unit configurations, and column headers.
4. **Decimal separator**: European SAP systems use comma as decimal separator (`1.234,56` = 1234.56). The parser handles this, but locale detection should be explicit rather than assumed.
5. **Encoding**: SAP exports can be Latin-1, UTF-8, or UTF-8 with BOM depending on client configuration. The parser tries UTF-8-sig first, falls back to Latin-1.

---

## 2. Utility electricity

### What I researched

Utility portal CSV exports vary by provider but share common patterns. I looked at:

- **ComEd (US, Midwest)**: Their "View Account Usage Data" portal exports CSVs with fields: billing period start/end, days in period, total kWh, on-peak kWh, off-peak kWh, billing demand (kW), monthly peak demand, rate code. Billing periods are typically 28–32 days and do NOT align with calendar months.
- **UK utilities (EDF, E.ON, British Gas)**: Smart meter data exports use similar structures. Key difference: UK uses half-hourly interval data for large commercial accounts, which would need aggregation to billing period.
- **Green Button standard**: A US Department of Energy initiative (OpenESB/ESPI) that standardizes utility data in XML format. Supported by some US utilities but not universal; UK and European utilities generally do not support it.

**Key insight from research**: Billing periods are the fundamental unit of utility data, not calendar months. A bill dated February 15 may cover Jan 18 → Feb 16 (30 days). ESG platforms that force this into "January" or "February" make an allocation assumption that is not in the source data.

### Sample data rationale

The sample (`utility_electricity_sample.csv`) uses ComEd-inspired column names and includes:
- Three accounts/facilities across two meter groups per Birmingham Factory
- Billing periods starting Jan 3 (not Jan 1) — realistic; utilities don't reset on the 1st
- Variable billing period lengths (29, 29, 32 days) — real utility billing cycles drift
- One zero-kWh row for London HQ in March — triggers the `zero_value` flag. This is realistic: a meter reading of zero often indicates a read failure or a vacant facility during refurbishment.
- Peak and off-peak split — ComEd's TOU (time-of-use) rates expose this. The prototype stores it in `extra` but doesn't use it for emissions (total kWh is used).
- Demand (kW) column — included because it appears in real exports; stored in `extra` for future market-based calculations.

### What would break in real deployment

1. **Half-hourly interval data**: Large commercial accounts in the UK receive HH (half-hourly) interval data, not billing summary. This would require aggregation logic before creating EmissionRecords.
2. **Estimated reads**: Utility CSVs often include an "Estimated" / "Actual" flag per reading. Estimated reads should be flagged for analyst review.
3. **Multi-fuel utilities**: Some utility accounts include gas and electricity on the same bill. The current parser assumes electricity only.
4. **Negative kWh (export)**: Facilities with solar panels or CHP may have negative kWh in some periods (net export to grid). This is legitimate and should not be flagged as zero_value.
5. **Currency / tariff structure**: Demand charges, capacity charges, and network charges appear in bills but are not kWh consumption. Some exports mix these in the same file.

---

## 3. Corporate travel

### What I researched

Corporate travel management platforms (TMCs) provide booking data in various formats:

- **Navan (formerly TripActions)**: Their reporting suite exports CSVs with one row per booking segment. Flights include origin/destination airports, cabin class, distance (sometimes provided, sometimes not). Hotels include check-in/check-out dates and city. Ground transport includes mode and distance.
- **Concur Travel & Expense**: Similar structure, but Concur's expense data can include non-travel expenses. The travel module specifically provides trip segments. Concur supports API access via OAuth 2.0 + REST (v4 API), but the API is complex and requires enterprise credentials.
- **IATA airport codes**: The standard for identifying airports (LHR, JFK, DXB). When platforms provide origin/destination as airport codes but not distance, Haversine can estimate great-circle distance. A public dataset of airport coordinates is available at github.com/datasets/airport-codes.
- **Emission factors**: DEFRA 2023 GHG Conversion Factors for Company Reporting provides per-km emission factors by cabin class including radiative forcing uplift. Note: DEFRA's factor already includes an indirect radiative forcing multiplier (1.891) applied to the CO2 figure, accounting for non-CO2 climate effects of aviation.

### Sample data rationale

The sample (`travel_sample.csv`) includes:
- One employee (EMP-0042) with a LHR→JFK flight, 3-night hotel, and two ground transport legs — a complete business trip
- One business class flight (EMP-0117, LHR→DXB) to show different emission factor
- One flight with distance provided (EMP-0089, LHR→SIN: 10,841 km) vs distance absent (other legs)
- Multi-leg trip (EMP-0089: LHR→SIN→BOM→LHR) — each leg is a separate row
- One flight with an unrecognized IATA code (EMP-0456: ZZZ) — triggers a parse failure to show error handling
- Ground transport with missing distance — triggers flagging for analyst review
- Hotel records with check-in/check-out dates

### What would break in real deployment

1. **Haversine underestimates**: Great-circle distance is 5–10% shorter than actual routed flight distance. DEFRA recommends not applying an additional uplift when using their radiative-forcing-inclusive factors, but this should be documented per client.
2. **Airport code gaps**: The prototype includes 20 major airports. A real deployment needs the full IATA dataset (~9,000 airports). Available as a public CSV; would be loaded into a database table.
3. **Hotel emission factors by country**: The global average (20.8 kgCO2e/room-night) masks significant variation. A hotel in India with coal-heavy grid has higher emissions than one in Norway with hydro power. Production would use country-level hotel emission factors.
4. **Personal vs business travel**: Corporate travel platforms often capture personal travel booked on the corporate card. Without a `business_purpose` field and filtering, personal travel would inflate Scope 3 Category 6.
5. **Rail distance**: Navan/Concur sometimes provide ground transport distances, sometimes not. Train distances should use routing distance, not straight-line.
6. **Currency normalization**: Travel cost data uses different currencies. Not used for emissions, but useful for cost-per-tonne analysis.
