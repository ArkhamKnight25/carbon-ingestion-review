"""Parsers for SAP fuel CSV, utility electricity CSV, corporate travel CSV.

Each parser returns (rows, errors) where:
  rows = list of dicts with normalized + raw fields ready for EmissionRecord creation
  errors = list of {row, field, message}
"""
import csv
import io
import re
from datetime import datetime, date
from decimal import Decimal, InvalidOperation

from .airports import airport_distance, AIRPORTS


# -- helpers ----------------------------------------------------------------

def _decode_bytes(file_bytes: bytes) -> str:
    for enc in ('utf-8-sig', 'utf-8', 'latin-1', 'cp1252'):
        try:
            return file_bytes.decode(enc)
        except UnicodeDecodeError:
            continue
    return file_bytes.decode('utf-8', errors='replace')


def _parse_decimal(value, allow_negative=True):
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    s = s.replace(' ', '')
    # European format: 1.234,56 -> 1234.56
    if ',' in s and '.' in s:
        if s.rfind(',') > s.rfind('.'):
            s = s.replace('.', '').replace(',', '.')
        else:
            s = s.replace(',', '')
    elif ',' in s:
        if re.match(r'^-?\d{1,3}(,\d{3})+$', s):
            s = s.replace(',', '')
        else:
            s = s.replace(',', '.')
    try:
        d = Decimal(s)
        if not allow_negative and d < 0:
            d = -d
        return d
    except InvalidOperation:
        return None


def _parse_date(value):
    if not value:
        return None
    s = str(value).strip()
    fmts = [
        '%Y-%m-%d', '%d.%m.%Y', '%d/%m/%Y', '%m/%d/%Y',
        '%d-%m-%Y', '%Y/%m/%d', '%d.%m.%y', '%d/%m/%y',
    ]
    for f in fmts:
        try:
            return datetime.strptime(s, f).date()
        except ValueError:
            continue
    return None


def _normalize_header(h: str) -> str:
    return re.sub(r'[^a-z0-9]', '_', h.strip().lower()).strip('_')


# -- SAP fuel ---------------------------------------------------------------

SAP_HEADER_MAP = {
    # posting date
    'buchungsdatum': 'posting_date', 'posting_date': 'posting_date',
    'pstng_date': 'posting_date', 'budat': 'posting_date',
    'posting': 'posting_date', 'date_posted': 'posting_date',
    # document date
    'belegdatum': 'document_date', 'document_date': 'document_date',
    'doc_date': 'document_date', 'bldat': 'document_date',
    # quantity
    'menge': 'quantity', 'quantity': 'quantity', 'qty': 'quantity',
    'menge_in_erfassungs_me': 'quantity', 'entry_quantity': 'quantity',
    'qty_in_unit_of_entry': 'quantity', 'mengeeh': 'quantity',
    # unit of measure
    'mengeneinheit': 'unit', 'unit_of_measure': 'unit', 'base_unit': 'unit',
    'unit': 'unit', 'meins': 'unit', 'uom': 'unit', 'erfme': 'unit',
    'unit_of_entry': 'unit',
    # plant
    'werk': 'plant', 'plant': 'plant', 'plant_code': 'plant',
    'werks': 'plant', 'plnt': 'plant', 'site': 'plant',
    # movement type
    'bewegungsart': 'movement_type', 'movement_type': 'movement_type',
    'bwart': 'movement_type', 'mvt_type': 'movement_type', 'mvt': 'movement_type',
    'mov_type': 'movement_type',
    # material
    'material': 'material', 'material_number': 'material', 'matnr': 'material',
    'material_no': 'material', 'sku': 'material',
    'materialkurztext': 'material_text', 'material_description': 'material_text',
    'material_desc': 'material_text', 'maktx': 'material_text', 'description': 'material_text',
    # vendor
    'lieferant': 'vendor', 'vendor': 'vendor', 'lifnr': 'vendor', 'supplier': 'vendor',
}

FUEL_MOVEMENT_TYPES = {'261', '262', '201', '202', '551', '552', '281', '282'}

FUEL_MATERIAL_MAP = {
    # material_number prefix or substring -> activity_key
    'D000': 'diesel_avg_biofuel_blend',
    'DIESEL': 'diesel_avg_biofuel_blend',
    'G000': 'natural_gas',
    'GAS': 'natural_gas',
    'P000': 'petrol_avg_biofuel_blend',
    'PETROL': 'petrol_avg_biofuel_blend',
    'HO00': 'heating_oil',
    'HEAT': 'heating_oil',
    'LPG': 'lpg',
}

UNIT_NORMAL = {
    'L': 'litre', 'LTR': 'litre', 'LITRE': 'litre', 'LITER': 'litre',
    'GAL': 'litre',  # gallon US -> litre, with conversion
    'M3': 'm3', 'CBM': 'm3', 'NM3': 'm3',
    'KG': 'kg', 'KGM': 'kg', 'TO': 'kg',
    'KWH': 'kWh',
}

UNIT_FACTOR = {
    'GAL': Decimal('3.78541'),
    'TO': Decimal('1000'),
}


def _detect_delimiter(text: str) -> str:
    head = text.splitlines()[0] if text else ''
    if head.count(';') > head.count(','):
        return ';'
    if head.count('\t') > head.count(','):
        return '\t'
    return ','


def _resolve_material_activity(material_number, material_text):
    text = (material_text or '').upper()
    code = (material_number or '').upper()
    for key, act in FUEL_MATERIAL_MAP.items():
        if code.startswith(key) or key in code or key in text:
            return act
    return None


def parse_sap_fuel(file_bytes: bytes, plant_to_facility: dict, factor_lookup) -> tuple:
    """plant_to_facility: dict[plant_code -> Facility]
       factor_lookup: callable(activity_key) -> EmissionFactor or None
    """
    text = _decode_bytes(file_bytes)
    delim = _detect_delimiter(text)
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    headers_raw = next(reader, [])
    headers = [_normalize_header(h) for h in headers_raw]
    mapped = [SAP_HEADER_MAP.get(h, h) for h in headers]

    rows, errors = [], []
    for idx, row in enumerate(reader, start=2):
        if not any(c.strip() for c in row):
            continue
        raw = {headers_raw[i]: row[i] if i < len(row) else '' for i in range(len(headers_raw))}
        d = {mapped[i]: row[i] if i < len(row) else '' for i in range(len(mapped))}

        mvt = str(d.get('movement_type', '')).strip()
        if mvt and mvt not in FUEL_MOVEMENT_TYPES:
            errors.append({'row': idx, 'field': 'movement_type',
                           'message': f"Skipped movement_type={mvt} (not fuel consumption)"})
            continue

        qty = _parse_decimal(d.get('quantity'), allow_negative=True)
        if qty is None:
            errors.append({'row': idx, 'field': 'quantity', 'message': 'Missing/unparseable quantity'})
            continue

        flags = []
        if qty < 0:
            flags.append('negative_quantity_taken_as_return')
            qty = -qty

        unit_raw = str(d.get('unit', '')).strip().upper() or 'L'
        unit_norm = UNIT_NORMAL.get(unit_raw, unit_raw.lower())
        qty_norm = qty
        if unit_raw in UNIT_FACTOR:
            qty_norm = qty * UNIT_FACTOR[unit_raw]

        plant = str(d.get('plant', '')).strip()
        facility = plant_to_facility.get(plant)
        if not facility:
            flags.append('missing_facility')

        posting = _parse_date(d.get('posting_date')) or _parse_date(d.get('document_date'))
        if not posting:
            errors.append({'row': idx, 'field': 'posting_date', 'message': 'Missing/unparseable posting date'})
            continue

        activity_key = _resolve_material_activity(d.get('material'), d.get('material_text'))
        if not activity_key:
            errors.append({'row': idx, 'field': 'material',
                           'message': f"Unknown material '{d.get('material')}' — cannot pick emission factor"})
            continue
        factor = factor_lookup(activity_key)
        if not factor:
            errors.append({'row': idx, 'field': 'material',
                           'message': f"No emission factor seeded for activity '{activity_key}'"})
            continue

        if factor.unit != unit_norm:
            flags.append(f'unit_mismatch_{unit_norm}_vs_{factor.unit}')

        co2e = (qty_norm * factor.factor).quantize(Decimal('0.0001'))

        scope = 1
        category = factor.category

        rows.append({
            'raw': raw,
            'source_row_number': idx,
            'scope': scope,
            'category': category,
            'activity_start': posting,
            'activity_end': posting,
            'quantity_raw': qty,
            'unit_raw': unit_raw,
            'quantity_normalized': qty_norm,
            'unit_normalized': unit_norm,
            'emission_factor': factor,
            'co2e_kg': co2e,
            'facility': facility,
            'flags': flags,
            'extra': {
                'movement_type': mvt,
                'plant_code': plant,
                'material_number': d.get('material'),
                'material_text': d.get('material_text'),
                'vendor': d.get('vendor'),
            },
        })

    return rows, errors


# -- Utility electricity ----------------------------------------------------

UTILITY_HEADER_MAP = {
    # account
    'account': 'account', 'account_number': 'account', 'account_id': 'account',
    'account_no': 'account', 'customer_number': 'account', 'mpan': 'account',
    'customer_id': 'account', 'supply_number': 'account',
    # meter
    'meter': 'meter_id', 'meter_id': 'meter_id', 'meter_number': 'meter_id',
    'meter_no': 'meter_id', 'msn': 'meter_id', 'meter_serial': 'meter_id',
    'meter_point': 'meter_id',
    # site/facility
    'site': 'site', 'site_name': 'site', 'facility': 'site', 'service_address': 'site',
    'location': 'site', 'premise': 'site', 'address': 'site',
    'service_location': 'site',
    # period start
    'billing_period_start': 'period_start', 'period_start': 'period_start',
    'read_date_start': 'period_start', 'start_date': 'period_start',
    'service_period_start': 'period_start', 'from_date': 'period_start',
    'period_from': 'period_start', 'reading_start': 'period_start',
    # period end
    'billing_period_end': 'period_end', 'period_end': 'period_end',
    'read_date_end': 'period_end', 'end_date': 'period_end',
    'service_period_end': 'period_end', 'to_date': 'period_end',
    'period_to': 'period_end', 'reading_end': 'period_end',
    # usage kWh
    'usage_kwh': 'usage_kwh', 'total_kwh': 'usage_kwh', 'kwh': 'usage_kwh',
    'consumption_kwh': 'usage_kwh', 'usage': 'usage_kwh', 'consumption': 'usage_kwh',
    'energy_kwh': 'usage_kwh', 'kwh_used': 'usage_kwh', 'total_consumption': 'usage_kwh',
    'electricity_kwh': 'usage_kwh', 'units': 'usage_kwh',
    # peak/offpeak
    'on_peak_kwh': 'on_peak_kwh', 'peak_kwh': 'on_peak_kwh', 'peak': 'on_peak_kwh',
    'off_peak_kwh': 'off_peak_kwh', 'offpeak_kwh': 'off_peak_kwh', 'off_peak': 'off_peak_kwh',
    # demand
    'demand_kw': 'demand_kw', 'billing_demand_kw': 'demand_kw', 'peak_demand_kw': 'demand_kw',
    'max_demand': 'demand_kw', 'kw_demand': 'demand_kw',
    # tariff
    'tariff': 'tariff', 'rate_code': 'tariff', 'rate_class': 'tariff',
    'tariff_code': 'tariff', 'rate_schedule': 'tariff', 'plan': 'tariff',
    # days
    'days': 'days', 'days_in_period': 'days', 'billing_days': 'days',
    'period_days': 'days', 'number_of_days': 'days',
}


def _match_facility(site_name, facilities_by_name):
    if not site_name:
        return None
    s = site_name.strip().lower()
    for name, f in facilities_by_name.items():
        if s == name.lower() or s in name.lower() or name.lower() in s:
            return f
    return None


def parse_utility_electricity(file_bytes: bytes, facilities_by_name: dict, factor_lookup) -> tuple:
    text = _decode_bytes(file_bytes)
    delim = _detect_delimiter(text)
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    headers_raw = next(reader, [])
    headers = [_normalize_header(h) for h in headers_raw]
    mapped = [UTILITY_HEADER_MAP.get(h, h) for h in headers]

    factor = factor_lookup('electricity_uk_grid')
    rows, errors = [], []
    for idx, row in enumerate(reader, start=2):
        if not any(c.strip() for c in row):
            continue
        raw = {headers_raw[i]: row[i] if i < len(row) else '' for i in range(len(headers_raw))}
        d = {mapped[i]: row[i] if i < len(row) else '' for i in range(len(mapped))}

        usage = _parse_decimal(d.get('usage_kwh'), allow_negative=True)
        if usage is None:
            errors.append({'row': idx, 'field': 'usage_kwh', 'message': 'Missing/unparseable usage'})
            continue

        flags = []
        if usage == 0:
            flags.append('zero_value')
        elif usage < 0:
            flags.append('negative_export')

        start = _parse_date(d.get('period_start'))
        end = _parse_date(d.get('period_end'))
        if not start or not end:
            errors.append({'row': idx, 'field': 'period', 'message': 'Missing billing period dates'})
            continue
        if end < start:
            errors.append({'row': idx, 'field': 'period', 'message': 'period_end before period_start'})
            continue

        site = d.get('site') or d.get('account')
        facility = _match_facility(site, facilities_by_name)
        if not facility:
            flags.append('missing_facility')

        if not factor:
            errors.append({'row': idx, 'field': 'factor',
                           'message': 'electricity_uk_grid factor not seeded'})
            continue

        co2e = (usage * factor.factor).quantize(Decimal('0.0001'))

        rows.append({
            'raw': raw,
            'source_row_number': idx,
            'scope': 2,
            'category': 'scope2_electricity',
            'activity_start': start,
            'activity_end': end,
            'quantity_raw': usage,
            'unit_raw': 'kWh',
            'quantity_normalized': usage,
            'unit_normalized': 'kWh',
            'emission_factor': factor,
            'co2e_kg': co2e,
            'facility': facility,
            'flags': flags,
            'extra': {
                'meter_id': d.get('meter_id'),
                'tariff': d.get('tariff'),
                'demand_kw': d.get('demand_kw'),
                'on_peak_kwh': d.get('on_peak_kwh'),
                'off_peak_kwh': d.get('off_peak_kwh'),
                'days_in_period': d.get('days'),
                'site': site,
            },
        })
    return rows, errors


# -- Corporate travel -------------------------------------------------------

TRAVEL_HEADER_MAP = {
    # trip / reservation id
    'trip_id': 'trip_id', 'booking_id': 'trip_id', 'reservation_id': 'trip_id',
    'reservation_number': 'trip_id', 'pnr': 'trip_id', 'record_locator': 'trip_id',
    'confirmation_number': 'trip_id', 'ref': 'trip_id',
    # employee
    'employee_id': 'employee_id', 'traveler_id': 'employee_id', 'user_id': 'employee_id',
    'traveler': 'employee_id', 'passenger_id': 'employee_id', 'staff_id': 'employee_id',
    'emp_id': 'employee_id', 'pax_id': 'employee_id',
    # trip type
    'trip_type': 'trip_type', 'segment_type': 'trip_type', 'type': 'trip_type',
    'category': 'trip_type', 'product_type': 'trip_type', 'service_type': 'trip_type',
    # origin
    'origin': 'origin', 'origin_iata': 'origin', 'from_airport': 'origin',
    'departure_airport': 'origin', 'from': 'origin', 'origin_code': 'origin',
    # destination
    'destination': 'destination', 'destination_iata': 'destination', 'to_airport': 'destination',
    'arrival_airport': 'destination', 'to': 'destination', 'destination_code': 'destination',
    # dates
    'departure_date': 'departure_date', 'date': 'departure_date', 'start_date': 'departure_date',
    'dep_date': 'departure_date', 'travel_date': 'departure_date', 'segment_date': 'departure_date',
    'arrival_date': 'arrival_date', 'end_date': 'arrival_date', 'arr_date': 'arrival_date',
    'return_date': 'arrival_date',
    # hotel dates
    'checkin_date': 'checkin_date', 'check_in': 'checkin_date',
    'check_in_date': 'checkin_date', 'arrival': 'checkin_date',
    'checkout_date': 'checkout_date', 'check_out': 'checkout_date',
    'check_out_date': 'checkout_date', 'departure': 'checkout_date',
    # distance (km only — miles would need value conversion, not aliased)
    'distance_km': 'distance_km', 'distance': 'distance_km', 'km': 'distance_km',
    'segment_distance_km': 'distance_km',
    # cabin
    'cabin_class': 'cabin_class', 'class_of_service': 'cabin_class', 'cabin': 'cabin_class',
    'service_class': 'cabin_class', 'fare_class': 'cabin_class', 'class': 'cabin_class',
    # nights
    'nights': 'nights', 'room_nights': 'nights', 'number_of_nights': 'nights',
    'duration_nights': 'nights', 'stay_length': 'nights',
    # ground mode
    'mode': 'mode', 'ground_mode': 'mode', 'transport_mode': 'mode',
    'transportation': 'mode', 'vehicle_type': 'mode',
    # city / hotel
    'city': 'city', 'hotel_city': 'city', 'location': 'city', 'destination_city': 'city',
    'hotel_name': 'hotel_name', 'property_name': 'hotel_name', 'hotel': 'hotel_name',
    'lodging_name': 'hotel_name',
}

CABIN_TO_FACTOR = {
    # economy
    'economy': 'flight_long_economy', 'eco': 'flight_long_economy',
    'coach': 'flight_long_economy', 'coach_class': 'flight_long_economy',
    'y': 'flight_long_economy', 'm': 'flight_long_economy', 'h': 'flight_long_economy',
    'k': 'flight_long_economy', 'l': 'flight_long_economy', 'q': 'flight_long_economy',
    'standard': 'flight_long_economy',
    # premium economy
    'premium': 'flight_long_premium', 'premium_economy': 'flight_long_premium',
    'premium economy': 'flight_long_premium', 'prem_economy': 'flight_long_premium',
    'w': 'flight_long_premium', 's': 'flight_long_premium',
    # business
    'business': 'flight_long_business', 'biz': 'flight_long_business',
    'business_class': 'flight_long_business', 'j': 'flight_long_business',
    'c': 'flight_long_business', 'd': 'flight_long_business', 'i': 'flight_long_business',
    'club': 'flight_long_business',
    # first
    'first': 'flight_long_first', 'first_class': 'flight_long_first',
    'f': 'flight_long_first', 'a': 'flight_long_first', 'p': 'flight_long_first',
}

GROUND_MODE_FACTOR = {
    'taxi': 'taxi_regular', 'cab': 'taxi_regular', 'car': 'taxi_regular',
    'car_hire': 'taxi_regular', 'rental_car': 'taxi_regular',
    'uber': 'taxi_regular', 'lyft': 'taxi_regular', 'rideshare': 'taxi_regular',
    'ride_share': 'taxi_regular',
    'rail': 'rail_national', 'train': 'rail_national', 'tgv': 'rail_national',
    'eurostar': 'rail_national', 'metro': 'rail_national', 'subway': 'rail_national',
}


def parse_travel(file_bytes: bytes, factor_lookup) -> tuple:
    text = _decode_bytes(file_bytes)
    delim = _detect_delimiter(text)
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    headers_raw = next(reader, [])
    headers = [_normalize_header(h) for h in headers_raw]
    mapped = [TRAVEL_HEADER_MAP.get(h, h) for h in headers]

    rows, errors = [], []
    for idx, row in enumerate(reader, start=2):
        if not any(c.strip() for c in row):
            continue
        raw = {headers_raw[i]: row[i] if i < len(row) else '' for i in range(len(headers_raw))}
        d = {mapped[i]: row[i] if i < len(row) else '' for i in range(len(mapped))}

        trip_type = (d.get('trip_type') or '').strip().lower()
        if trip_type in ('flight', 'air', 'flights'):
            row_data = _parse_flight(idx, raw, d, factor_lookup, errors)
        elif trip_type in ('hotel', 'lodging', 'accommodation'):
            row_data = _parse_hotel(idx, raw, d, factor_lookup, errors)
        elif trip_type in ('ground', 'taxi', 'rail', 'train', 'car'):
            row_data = _parse_ground(idx, raw, d, factor_lookup, errors)
        else:
            errors.append({'row': idx, 'field': 'trip_type',
                           'message': f"Unknown trip_type '{trip_type}'"})
            continue

        if row_data:
            rows.append(row_data)
    return rows, errors


def _parse_flight(idx, raw, d, factor_lookup, errors):
    flags = []
    origin = (d.get('origin') or '').strip().upper()
    dest = (d.get('destination') or '').strip().upper()
    dep = _parse_date(d.get('departure_date'))
    if not dep:
        errors.append({'row': idx, 'field': 'departure_date', 'message': 'Missing departure date'})
        return None

    distance = _parse_decimal(d.get('distance_km'), allow_negative=False)
    if distance is None:
        if origin and dest:
            est = airport_distance(origin, dest)
            if est is None:
                errors.append({'row': idx, 'field': 'airports',
                               'message': f"Unknown IATA code(s): {origin}, {dest}"})
                return None
            distance = Decimal(str(est))
            flags.append('estimated_distance')
        else:
            errors.append({'row': idx, 'field': 'distance',
                           'message': 'No distance and no airport pair'})
            return None

    cabin = (d.get('cabin_class') or 'economy').strip().lower()
    activity_key = CABIN_TO_FACTOR.get(cabin)
    if not activity_key:
        flags.append(f'unknown_cabin_{cabin}_defaulted_economy')
        activity_key = 'flight_long_economy'
    factor = factor_lookup(activity_key)
    if not factor:
        errors.append({'row': idx, 'field': 'cabin_class',
                       'message': f"No factor for {activity_key}"})
        return None

    co2e = (distance * factor.factor).quantize(Decimal('0.0001'))
    end = _parse_date(d.get('arrival_date')) or dep
    return {
        'raw': raw,
        'source_row_number': idx,
        'scope': 3,
        'category': 'scope3_cat6_flight',
        'activity_start': dep,
        'activity_end': end,
        'quantity_raw': _parse_decimal(d.get('distance_km')) or distance,
        'unit_raw': 'km',
        'quantity_normalized': distance,
        'unit_normalized': 'km',
        'emission_factor': factor,
        'co2e_kg': co2e,
        'facility': None,
        'flags': flags,
        'extra': {
            'employee_id': d.get('employee_id'),
            'trip_id': d.get('trip_id'),
            'origin_iata': origin,
            'destination_iata': dest,
            'cabin_class': cabin,
            'distance_estimated': 'estimated_distance' in flags,
        },
    }


def _parse_hotel(idx, raw, d, factor_lookup, errors):
    flags = []
    checkin = _parse_date(d.get('checkin_date')) or _parse_date(d.get('departure_date'))
    checkout = _parse_date(d.get('checkout_date')) or _parse_date(d.get('arrival_date'))
    nights = _parse_decimal(d.get('nights'), allow_negative=False)
    if not nights and checkin and checkout:
        nights = Decimal((checkout - checkin).days)
    if not nights or nights <= 0:
        errors.append({'row': idx, 'field': 'nights',
                       'message': 'Missing/zero nights and no usable checkin/checkout pair'})
        return None
    if not checkin:
        errors.append({'row': idx, 'field': 'checkin_date', 'message': 'Missing checkin date'})
        return None
    if not checkout:
        checkout = checkin

    factor = factor_lookup('hotel_global_avg')
    if not factor:
        errors.append({'row': idx, 'field': 'factor', 'message': 'No hotel factor seeded'})
        return None

    co2e = (nights * factor.factor).quantize(Decimal('0.0001'))
    return {
        'raw': raw,
        'source_row_number': idx,
        'scope': 3,
        'category': 'scope3_cat6_hotel',
        'activity_start': checkin,
        'activity_end': checkout,
        'quantity_raw': nights,
        'unit_raw': 'room_night',
        'quantity_normalized': nights,
        'unit_normalized': 'room_night',
        'emission_factor': factor,
        'co2e_kg': co2e,
        'facility': None,
        'flags': flags,
        'extra': {
            'employee_id': d.get('employee_id'),
            'trip_id': d.get('trip_id'),
            'hotel_name': d.get('hotel_name'),
            'city': d.get('city'),
        },
    }


def _parse_ground(idx, raw, d, factor_lookup, errors):
    flags = []
    mode = (d.get('mode') or d.get('trip_type') or '').strip().lower()
    dep = _parse_date(d.get('departure_date'))
    if not dep:
        errors.append({'row': idx, 'field': 'departure_date', 'message': 'Missing date'})
        return None
    distance = _parse_decimal(d.get('distance_km'), allow_negative=False)
    if distance is None:
        errors.append({'row': idx, 'field': 'distance_km',
                       'message': f"Ground transport ({mode}) missing distance — flagged for review"})
        return None

    activity_key = GROUND_MODE_FACTOR.get(mode, 'taxi_regular')
    factor = factor_lookup(activity_key)
    if not factor:
        errors.append({'row': idx, 'field': 'mode', 'message': f"No factor for {activity_key}"})
        return None
    co2e = (distance * factor.factor).quantize(Decimal('0.0001'))
    return {
        'raw': raw,
        'source_row_number': idx,
        'scope': 3,
        'category': 'scope3_cat6_ground',
        'activity_start': dep,
        'activity_end': dep,
        'quantity_raw': distance,
        'unit_raw': 'km',
        'quantity_normalized': distance,
        'unit_normalized': 'km',
        'emission_factor': factor,
        'co2e_kg': co2e,
        'facility': None,
        'flags': flags,
        'extra': {
            'employee_id': d.get('employee_id'),
            'trip_id': d.get('trip_id'),
            'mode': mode,
            'city': d.get('city'),
        },
    }
