from decimal import Decimal
from django.db.models import Sum, Count, Q
from django.utils import timezone
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from .models import (
    Tenant, Facility, PlantCodeMapping, EmissionFactor,
    IngestionBatch, EmissionRecord, AuditEvent,
)
from .serializers import (
    TenantSerializer, FacilitySerializer, PlantCodeMappingSerializer,
    EmissionFactorSerializer, IngestionBatchSerializer,
    EmissionRecordSerializer, AuditEventSerializer,
)


def _current_tenant(request):
    return Tenant.objects.first()


class TenantViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = TenantSerializer

    def get_queryset(self):
        return Tenant.objects.all()


class FacilityViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = FacilitySerializer

    def get_queryset(self):
        tenant = _current_tenant(self.request)
        return Facility.objects.filter(tenant=tenant) if tenant else Facility.objects.none()


class EmissionFactorViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = EmissionFactorSerializer
    queryset = EmissionFactor.objects.all()


class PlantCodeMappingViewSet(viewsets.ModelViewSet):
    serializer_class = PlantCodeMappingSerializer
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        tenant = _current_tenant(self.request)
        if not tenant:
            return PlantCodeMapping.objects.none()
        return PlantCodeMapping.objects.filter(tenant=tenant).select_related('facility')

    def perform_create(self, serializer):
        tenant = _current_tenant(self.request)
        serializer.save(tenant=tenant)


class BatchViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = IngestionBatchSerializer
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['uploaded_at', 'status']
    ordering = ['-uploaded_at']

    def get_queryset(self):
        tenant = _current_tenant(self.request)
        return IngestionBatch.objects.filter(tenant=tenant) if tenant else IngestionBatch.objects.none()

    @action(detail=True, methods=['post'])
    def lock(self, request, pk=None):
        batch = self.get_object()
        pending = batch.emissions.filter(status__in=['pending', 'flagged'])
        if pending.exists():
            return Response(
                {'detail': f'{pending.count()} records still pending/flagged. Resolve before lock.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if batch.status == 'locked':
            return Response({'detail': 'Already locked.'}, status=status.HTTP_400_BAD_REQUEST)

        approved_qs = batch.emissions.filter(status='approved')
        approved_qs.update(status='locked')
        batch.status = 'locked'
        batch.locked_at = timezone.now()
        batch.locked_by = request.user if request.user.is_authenticated else None
        batch.save()

        AuditEvent.objects.create(
            batch=batch,
            action='batch_locked',
            actor=request.user if request.user.is_authenticated else None,
            after_value={'locked_at': batch.locked_at.isoformat(), 'records_locked': approved_qs.count()},
        )
        return Response({'status': 'locked', 'records_locked': approved_qs.count()})

    @action(detail=True, methods=['get'])
    def audit(self, request, pk=None):
        batch = self.get_object()
        events = AuditEvent.objects.filter(
            Q(batch=batch) | Q(emission_record__batch=batch)
        ).order_by('-timestamp')[:500]
        return Response(AuditEventSerializer(events, many=True).data)


EDITABLE_FIELDS = {
    'quantity_normalized', 'unit_normalized', 'category',
    'activity_start', 'activity_end', 'facility_id', 'review_note',
}


class EmissionRecordViewSet(viewsets.ModelViewSet):
    serializer_class = EmissionRecordSerializer
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['activity_start', 'co2e_kg', 'status']
    ordering = ['-activity_start']
    http_method_names = ['get', 'patch', 'post', 'head', 'options']

    def get_queryset(self):
        tenant = _current_tenant(self.request)
        if not tenant:
            return EmissionRecord.objects.none()
        qs = EmissionRecord.objects.filter(tenant=tenant).select_related(
            'facility', 'batch', 'raw_record', 'emission_factor'
        )
        params = self.request.query_params
        if params.get('batch'):
            qs = qs.filter(batch_id=params['batch'])
        if params.get('status'):
            qs = qs.filter(status=params['status'])
        if params.get('scope'):
            qs = qs.filter(scope=params['scope'])
        if params.get('category'):
            qs = qs.filter(category=params['category'])
        return qs

    def partial_update(self, request, *args, **kwargs):
        record = self.get_object()
        if record.status == 'locked':
            return Response({'detail': 'Locked records cannot be edited.'},
                            status=status.HTTP_400_BAD_REQUEST)

        incoming = {k: v for k, v in request.data.items() if k in EDITABLE_FIELDS}
        if not incoming:
            return Response({'detail': f'No editable fields. Allowed: {sorted(EDITABLE_FIELDS)}'},
                            status=status.HTTP_400_BAD_REQUEST)

        before = {k: getattr(record, k) if k != 'facility_id' else (record.facility_id) for k in incoming}
        for k in ('activity_start', 'activity_end'):
            if k in before and before[k] is not None:
                before[k] = before[k].isoformat()
        for k in ('quantity_normalized',):
            if k in before and before[k] is not None:
                before[k] = str(before[k])

        for k, v in incoming.items():
            setattr(record, k, v)

        if 'quantity_normalized' in incoming and record.emission_factor:
            from decimal import Decimal
            try:
                qty = Decimal(str(record.quantity_normalized))
                record.co2e_kg = (qty * record.emission_factor.factor).quantize(Decimal('0.0001'))
            except Exception:
                pass

        record.save()

        AuditEvent.objects.create(
            emission_record=record,
            action='edited',
            before_value=before,
            after_value=incoming,
            actor=request.user if request.user.is_authenticated else None,
            note=request.data.get('note', ''),
        )
        return Response(EmissionRecordSerializer(record).data)

    def _change_status(self, request, new_status, note=''):
        record = self.get_object()
        before = {'status': record.status, 'flags': record.flags}
        record.status = new_status
        if note:
            record.review_note = note
        record.save()
        AuditEvent.objects.create(
            emission_record=record,
            action='status_change',
            before_value=before,
            after_value={'status': new_status, 'note': note},
            actor=request.user if request.user.is_authenticated else None,
            note=note,
        )
        return Response(EmissionRecordSerializer(record).data)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        return self._change_status(request, 'approved', request.data.get('note', ''))

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        return self._change_status(request, 'rejected', request.data.get('note', ''))

    @action(detail=True, methods=['post'])
    def flag(self, request, pk=None):
        record = self.get_object()
        reason = request.data.get('reason', 'manual_flag')
        before = {'status': record.status, 'flags': list(record.flags)}
        if reason not in record.flags:
            record.flags = list(record.flags) + [reason]
        record.status = 'flagged'
        record.review_note = request.data.get('note', record.review_note)
        record.save()
        AuditEvent.objects.create(
            emission_record=record,
            action='flagged',
            before_value=before,
            after_value={'status': record.status, 'flags': record.flags},
            actor=request.user if request.user.is_authenticated else None,
            note=request.data.get('note', ''),
        )
        return Response(EmissionRecordSerializer(record).data)

    @action(detail=True, methods=['get'])
    def audit(self, request, pk=None):
        record = self.get_object()
        events = record.audit_events.all()
        return Response(AuditEventSerializer(events, many=True).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard_stats(request):
    tenant = _current_tenant(request)
    if not tenant:
        return Response({'detail': 'No tenant.'}, status=400)

    qs = EmissionRecord.objects.filter(tenant=tenant)

    by_scope = {1: 0, 2: 0, 3: 0}
    for row in qs.values('scope').annotate(total=Sum('co2e_kg')):
        by_scope[row['scope']] = float(row['total'] or 0)

    by_category = list(
        qs.values('category').annotate(total=Sum('co2e_kg'), n=Count('id')).order_by('-total')
    )
    for row in by_category:
        row['total'] = float(row['total'] or 0)

    by_status = dict(qs.values_list('status').annotate(n=Count('id')))

    total = float(qs.aggregate(total=Sum('co2e_kg'))['total'] or 0)
    pending_review = qs.filter(status__in=['pending', 'flagged']).count()
    batches = IngestionBatch.objects.filter(tenant=tenant).count()

    recent = qs.order_by('-created_at')[:10]
    return Response({
        'total_co2e_kg': total,
        'total_co2e_tonnes': total / 1000.0,
        'by_scope': by_scope,
        'by_category': by_category,
        'by_status': by_status,
        'pending_review': pending_review,
        'total_records': qs.count(),
        'total_batches': batches,
        'recent': EmissionRecordSerializer(recent, many=True).data,
    })
