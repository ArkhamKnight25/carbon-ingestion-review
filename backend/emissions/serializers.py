from rest_framework import serializers
from .models import (
    Tenant, Facility, PlantCodeMapping, EmissionFactor,
    IngestionBatch, RawRecord, EmissionRecord, AuditEvent,
)


class FacilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Facility
        fields = ('id', 'name', 'country', 'grid_region')


class TenantSerializer(serializers.ModelSerializer):
    facilities = FacilitySerializer(many=True, read_only=True)

    class Meta:
        model = Tenant
        fields = ('id', 'name', 'slug', 'facilities')


class PlantCodeMappingSerializer(serializers.ModelSerializer):
    facility_name = serializers.CharField(source='facility.name', read_only=True)

    class Meta:
        model = PlantCodeMapping
        fields = ('id', 'plant_code', 'facility', 'facility_name')


class EmissionFactorSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmissionFactor
        fields = '__all__'


class IngestionBatchSerializer(serializers.ModelSerializer):
    uploaded_by_username = serializers.CharField(source='uploaded_by.username', read_only=True)

    class Meta:
        model = IngestionBatch
        fields = (
            'id', 'source_type', 'filename', 'file_hash', 'row_count',
            'success_count', 'error_count', 'parse_errors', 'status',
            'uploaded_by_username', 'uploaded_at', 'locked_at',
        )


class RawRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = RawRecord
        fields = ('id', 'source_row_number', 'raw_data')


class EmissionRecordSerializer(serializers.ModelSerializer):
    raw_data = serializers.JSONField(source='raw_record.raw_data', read_only=True)
    source_row_number = serializers.IntegerField(source='raw_record.source_row_number', read_only=True)
    facility_name = serializers.CharField(source='facility.name', read_only=True, default=None)
    batch_filename = serializers.CharField(source='batch.filename', read_only=True)
    source_type = serializers.CharField(source='batch.source_type', read_only=True)
    emission_factor_label = serializers.SerializerMethodField()

    class Meta:
        model = EmissionRecord
        fields = (
            'id', 'scope', 'category', 'activity_start', 'activity_end',
            'quantity_raw', 'unit_raw', 'quantity_normalized', 'unit_normalized',
            'co2e_kg', 'status', 'flags', 'review_note',
            'extra', 'facility_name', 'batch', 'batch_filename', 'source_type',
            'raw_data', 'source_row_number', 'emission_factor_label',
            'created_at', 'updated_at',
        )

    def get_emission_factor_label(self, obj):
        if obj.emission_factor:
            return f"{obj.emission_factor.activity_key} ({obj.emission_factor.factor} {obj.emission_factor.factor_unit}/{obj.emission_factor.unit})"
        return None


class AuditEventSerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(source='actor.username', read_only=True, default=None)

    class Meta:
        model = AuditEvent
        fields = (
            'id', 'action', 'before_value', 'after_value',
            'actor_username', 'note', 'timestamp',
        )
