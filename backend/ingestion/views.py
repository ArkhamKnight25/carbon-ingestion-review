import hashlib
import statistics
from decimal import Decimal

from django.db import transaction
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response

from emissions.models import (
    Tenant, Facility, PlantCodeMapping, EmissionFactor,
    IngestionBatch, RawRecord, EmissionRecord, AuditEvent,
)
from emissions.serializers import IngestionBatchSerializer
from .parsers import parse_sap_fuel, parse_utility_electricity, parse_travel


def _factor_lookup_factory():
    cache = {}

    def lookup(activity_key):
        if activity_key in cache:
            return cache[activity_key]
        f = EmissionFactor.objects.filter(activity_key=activity_key).order_by('-valid_from').first()
        cache[activity_key] = f
        return f
    return lookup


def _apply_outlier_flags(parsed_rows):
    """3-sigma flag within batch, per scope."""
    by_scope = {}
    for r in parsed_rows:
        by_scope.setdefault(r['scope'], []).append(r)
    for scope, group in by_scope.items():
        if len(group) < 5:
            continue
        values = [float(r['co2e_kg']) for r in group if r['co2e_kg'] > 0]
        if len(values) < 5:
            continue
        try:
            mean = statistics.mean(values)
            stdev = statistics.stdev(values)
        except statistics.StatisticsError:
            continue
        if stdev == 0:
            continue
        for r in group:
            v = float(r['co2e_kg'])
            if abs(v - mean) > 3 * stdev:
                if 'outlier' not in r['flags']:
                    r['flags'].append('outlier')


def _check_duplicate_periods(tenant, parsed_rows, source_type):
    """Flag billing period overlap for utility records (per meter)."""
    if source_type != 'UTILITY_ELEC':
        return
    seen_pairs = set()
    for r in parsed_rows:
        meter = (r.get('extra') or {}).get('meter_id') or ''
        key = (meter, r['activity_start'], r['activity_end'])
        if key in seen_pairs:
            r['flags'].append('duplicate_period_in_batch')
        seen_pairs.add(key)

        if meter:
            exists = EmissionRecord.objects.filter(
                tenant=tenant,
                extra__meter_id=meter,
                activity_start=r['activity_start'],
                activity_end=r['activity_end'],
            ).exists()
            if exists:
                r['flags'].append('billing_period_overlap')


SOURCE_PARSERS = {
    'SAP_FUEL': 'sap',
    'UTILITY_ELEC': 'utility',
    'TRAVEL': 'travel',
}


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def upload(request):
    source_type = request.data.get('source_type')
    if source_type not in SOURCE_PARSERS:
        return Response({'detail': f'source_type must be one of {list(SOURCE_PARSERS)}'},
                        status=status.HTTP_400_BAD_REQUEST)
    upload_file = request.FILES.get('file')
    if not upload_file:
        return Response({'detail': 'file is required'}, status=status.HTTP_400_BAD_REQUEST)

    file_bytes = upload_file.read()
    file_hash = hashlib.sha256(file_bytes).hexdigest()
    filename = upload_file.name

    tenant = Tenant.objects.first()
    if not tenant:
        return Response({'detail': 'No tenant seeded'}, status=status.HTTP_400_BAD_REQUEST)

    if IngestionBatch.objects.filter(tenant=tenant, file_hash=file_hash).exists():
        existing = IngestionBatch.objects.get(tenant=tenant, file_hash=file_hash)
        return Response(
            {'detail': 'Duplicate file (already uploaded).',
             'existing_batch_id': existing.id,
             'existing_filename': existing.filename},
            status=status.HTTP_409_CONFLICT,
        )

    factor_lookup = _factor_lookup_factory()

    if source_type == 'SAP_FUEL':
        plant_map = {
            pc.plant_code: pc.facility
            for pc in PlantCodeMapping.objects.filter(tenant=tenant).select_related('facility')
        }
        parsed_rows, parse_errors = parse_sap_fuel(file_bytes, plant_map, factor_lookup)
    elif source_type == 'UTILITY_ELEC':
        facilities_by_name = {f.name: f for f in Facility.objects.filter(tenant=tenant)}
        parsed_rows, parse_errors = parse_utility_electricity(file_bytes, facilities_by_name, factor_lookup)
    else:
        parsed_rows, parse_errors = parse_travel(file_bytes, factor_lookup)

    _apply_outlier_flags(parsed_rows)
    _check_duplicate_periods(tenant, parsed_rows, source_type)

    with transaction.atomic():
        batch = IngestionBatch.objects.create(
            tenant=tenant,
            source_type=source_type,
            filename=filename,
            file_hash=file_hash,
            row_count=len(parsed_rows) + len(parse_errors),
            success_count=len(parsed_rows),
            error_count=len(parse_errors),
            parse_errors=parse_errors,
            status='completed',
            uploaded_by=request.user if request.user.is_authenticated else None,
        )

        AuditEvent.objects.create(
            batch=batch,
            action='created',
            after_value={
                'filename': filename, 'source_type': source_type,
                'success_count': len(parsed_rows), 'error_count': len(parse_errors),
            },
            actor=request.user if request.user.is_authenticated else None,
        )

        for row in parsed_rows:
            raw = RawRecord.objects.create(
                batch=batch,
                source_row_number=row['source_row_number'],
                raw_data=row['raw'],
            )
            initial_status = 'flagged' if row['flags'] else 'pending'
            rec = EmissionRecord.objects.create(
                tenant=tenant,
                batch=batch,
                raw_record=raw,
                facility=row['facility'],
                scope=row['scope'],
                category=row['category'],
                activity_start=row['activity_start'],
                activity_end=row['activity_end'],
                quantity_raw=row['quantity_raw'],
                unit_raw=row['unit_raw'],
                quantity_normalized=row['quantity_normalized'],
                unit_normalized=row['unit_normalized'],
                emission_factor=row['emission_factor'],
                co2e_kg=row['co2e_kg'],
                status=initial_status,
                flags=row['flags'],
                extra=row['extra'],
            )
            if row['flags']:
                AuditEvent.objects.create(
                    emission_record=rec,
                    action='flagged',
                    after_value={'flags': row['flags']},
                )

    return Response(IngestionBatchSerializer(batch).data, status=status.HTTP_201_CREATED)
