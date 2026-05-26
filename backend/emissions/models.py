from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class Tenant(models.Model):
    name = models.CharField(max_length=200, unique=True)
    slug = models.SlugField(max_length=80, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Facility(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='facilities')
    name = models.CharField(max_length=200)
    country = models.CharField(max_length=2, default='GB')
    grid_region = models.CharField(max_length=80, default='UK')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('tenant', 'name')]

    def __str__(self):
        return f"{self.tenant.slug}/{self.name}"


class PlantCodeMapping(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='plant_codes')
    plant_code = models.CharField(max_length=8)
    facility = models.ForeignKey(Facility, on_delete=models.CASCADE, related_name='plant_codes')

    class Meta:
        unique_together = [('tenant', 'plant_code')]

    def __str__(self):
        return f"{self.plant_code} -> {self.facility.name}"


class EmissionFactor(models.Model):
    SCOPE_CHOICES = [(1, 'Scope 1'), (2, 'Scope 2'), (3, 'Scope 3')]

    category = models.CharField(max_length=64, db_index=True)
    activity_key = models.CharField(max_length=128, db_index=True)
    unit = models.CharField(max_length=32)
    factor = models.DecimalField(max_digits=14, decimal_places=6)
    factor_unit = models.CharField(max_length=64, default='kgCO2e')
    scope = models.IntegerField(choices=SCOPE_CHOICES)
    source = models.CharField(max_length=128, default='DEFRA 2023')
    valid_from = models.DateField()
    valid_to = models.DateField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=['activity_key', 'valid_from'])]

    def __str__(self):
        return f"{self.activity_key} = {self.factor} {self.factor_unit}/{self.unit}"


class IngestionBatch(models.Model):
    SOURCE_CHOICES = [
        ('SAP_FUEL', 'SAP fuel movements'),
        ('UTILITY_ELEC', 'Utility electricity'),
        ('TRAVEL', 'Corporate travel'),
    ]
    STATUS_CHOICES = [
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('locked', 'Locked'),
    ]

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='batches')
    source_type = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    filename = models.CharField(max_length=256)
    file_hash = models.CharField(max_length=64, db_index=True)
    row_count = models.IntegerField(default=0)
    success_count = models.IntegerField(default=0)
    error_count = models.IntegerField(default=0)
    parse_errors = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='processing')
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='locked_batches')

    class Meta:
        ordering = ['-uploaded_at']
        unique_together = [('tenant', 'file_hash')]

    def __str__(self):
        return f"{self.source_type}/{self.filename}"


class RawRecord(models.Model):
    """Immutable. Original parsed row stored as JSON."""
    batch = models.ForeignKey(IngestionBatch, on_delete=models.CASCADE, related_name='raw_records')
    source_row_number = models.IntegerField()
    raw_data = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['batch', 'source_row_number'])]


class EmissionRecord(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending review'),
        ('flagged', 'Flagged'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('locked', 'Locked'),
    ]
    SCOPE_CHOICES = [(1, 'Scope 1'), (2, 'Scope 2'), (3, 'Scope 3')]

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='emissions')
    batch = models.ForeignKey(IngestionBatch, on_delete=models.CASCADE, related_name='emissions')
    raw_record = models.OneToOneField(RawRecord, on_delete=models.CASCADE, related_name='emission')
    facility = models.ForeignKey(Facility, on_delete=models.SET_NULL, null=True, blank=True)

    scope = models.IntegerField(choices=SCOPE_CHOICES)
    category = models.CharField(max_length=64, db_index=True)
    activity_start = models.DateField()
    activity_end = models.DateField()

    quantity_raw = models.DecimalField(max_digits=18, decimal_places=4)
    unit_raw = models.CharField(max_length=32)
    quantity_normalized = models.DecimalField(max_digits=18, decimal_places=4)
    unit_normalized = models.CharField(max_length=32)

    emission_factor = models.ForeignKey(EmissionFactor, on_delete=models.PROTECT, null=True, blank=True)
    co2e_kg = models.DecimalField(max_digits=18, decimal_places=4)

    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='pending')
    flags = models.JSONField(default=list, blank=True)
    review_note = models.TextField(blank=True)

    extra = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['tenant', 'scope', 'activity_start']),
            models.Index(fields=['status']),
            models.Index(fields=['category']),
        ]
        ordering = ['-activity_start']

    def __str__(self):
        return f"{self.category} {self.co2e_kg}kg ({self.status})"


class AuditEvent(models.Model):
    """Append-only audit log."""
    ACTION_CHOICES = [
        ('created', 'Created'),
        ('status_change', 'Status change'),
        ('edited', 'Edited'),
        ('flagged', 'Flagged'),
        ('batch_locked', 'Batch locked'),
    ]

    emission_record = models.ForeignKey(
        EmissionRecord, on_delete=models.CASCADE, related_name='audit_events', null=True, blank=True
    )
    batch = models.ForeignKey(
        IngestionBatch, on_delete=models.CASCADE, related_name='audit_events', null=True, blank=True
    )
    action = models.CharField(max_length=32, choices=ACTION_CHOICES)
    before_value = models.JSONField(null=True, blank=True)
    after_value = models.JSONField(null=True, blank=True)
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    note = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-timestamp']
