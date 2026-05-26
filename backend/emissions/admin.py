from django.contrib import admin
from .models import (
    Tenant, Facility, PlantCodeMapping, EmissionFactor,
    IngestionBatch, RawRecord, EmissionRecord, AuditEvent,
)


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'created_at')


@admin.register(Facility)
class FacilityAdmin(admin.ModelAdmin):
    list_display = ('name', 'tenant', 'country', 'grid_region')
    list_filter = ('tenant', 'country')


@admin.register(PlantCodeMapping)
class PlantCodeMappingAdmin(admin.ModelAdmin):
    list_display = ('plant_code', 'tenant', 'facility')


@admin.register(EmissionFactor)
class EmissionFactorAdmin(admin.ModelAdmin):
    list_display = ('activity_key', 'category', 'scope', 'factor', 'unit', 'source', 'valid_from')
    list_filter = ('scope', 'category', 'source')


@admin.register(IngestionBatch)
class IngestionBatchAdmin(admin.ModelAdmin):
    list_display = ('filename', 'source_type', 'tenant', 'status', 'success_count', 'error_count', 'uploaded_at')
    list_filter = ('source_type', 'status')
    readonly_fields = ('file_hash', 'parse_errors')


@admin.register(EmissionRecord)
class EmissionRecordAdmin(admin.ModelAdmin):
    list_display = ('category', 'scope', 'co2e_kg', 'status', 'activity_start', 'facility')
    list_filter = ('scope', 'status', 'category')
    search_fields = ('category',)


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ('action', 'emission_record', 'batch', 'actor', 'timestamp')
    list_filter = ('action',)
    readonly_fields = ('before_value', 'after_value', 'timestamp')


admin.site.register(RawRecord)
