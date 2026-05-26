from datetime import date
from decimal import Decimal
import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from emissions.models import (
    Tenant, Facility, PlantCodeMapping, EmissionFactor,
)

User = get_user_model()


class Command(BaseCommand):
    help = "Seed reference data and demo user/tenant."

    def add_arguments(self, parser):
        parser.add_argument('--noinput', action='store_true')

    @transaction.atomic
    def handle(self, *args, **opts):
        admin_user, created = User.objects.get_or_create(
            username='admin',
            defaults={
                'email': 'admin@carbontrace.local',
                'is_staff': True,
                'is_superuser': True,
            },
        )
        if created:
            admin_user.set_password(os.environ.get('SEED_ADMIN_PASSWORD', 'admin123'))
            admin_user.save()
            self.stdout.write(self.style.SUCCESS('Created admin user (admin/admin123)'))

        analyst, created = User.objects.get_or_create(
            username='analyst',
            defaults={'email': 'analyst@carbontrace.local', 'is_staff': False},
        )
        if created:
            analyst.set_password('analyst123')
            analyst.save()
            self.stdout.write(self.style.SUCCESS('Created analyst user (analyst/analyst123)'))

        tenant, _ = Tenant.objects.get_or_create(
            slug='acme',
            defaults={'name': 'Acme Manufacturing Ltd'},
        )

        facilities_data = [
            ('Birmingham Factory', 'GB', 'UK'),
            ('Manchester Warehouse', 'GB', 'UK'),
            ('London HQ', 'GB', 'UK'),
        ]
        facility_map = {}
        for name, country, region in facilities_data:
            f, _ = Facility.objects.get_or_create(
                tenant=tenant, name=name,
                defaults={'country': country, 'grid_region': region},
            )
            facility_map[name] = f

        plant_mappings = [
            ('BHM1', 'Birmingham Factory'),
            ('MCR1', 'Manchester Warehouse'),
            ('LDN1', 'London HQ'),
        ]
        for code, fname in plant_mappings:
            PlantCodeMapping.objects.get_or_create(
                tenant=tenant, plant_code=code,
                defaults={'facility': facility_map[fname]},
            )

        factors = [
            # SAP fuel - Scope 1 (DEFRA 2023)
            dict(activity_key='diesel_avg_biofuel_blend', category='scope1_fuel_mobile',
                 unit='litre', factor=Decimal('2.51233'), scope=1),
            dict(activity_key='petrol_avg_biofuel_blend', category='scope1_fuel_mobile',
                 unit='litre', factor=Decimal('2.19352'), scope=1),
            dict(activity_key='natural_gas', category='scope1_fuel_stationary',
                 unit='m3', factor=Decimal('2.04400'), scope=1),
            dict(activity_key='heating_oil', category='scope1_fuel_stationary',
                 unit='litre', factor=Decimal('2.54603'), scope=1),
            dict(activity_key='lpg', category='scope1_fuel_stationary',
                 unit='kg', factor=Decimal('2.93903'), scope=1),

            # Utility - Scope 2 (DEFRA 2023 UK grid)
            dict(activity_key='electricity_uk_grid', category='scope2_electricity',
                 unit='kWh', factor=Decimal('0.20705'), scope=2),

            # Travel - Scope 3 cat 6 (DEFRA 2023)
            dict(activity_key='flight_short_economy', category='scope3_cat6_flight',
                 unit='km', factor=Decimal('0.15102'), scope=3),
            dict(activity_key='flight_long_economy', category='scope3_cat6_flight',
                 unit='km', factor=Decimal('0.14981'), scope=3),
            dict(activity_key='flight_long_premium', category='scope3_cat6_flight',
                 unit='km', factor=Decimal('0.23970'), scope=3),
            dict(activity_key='flight_long_business', category='scope3_cat6_flight',
                 unit='km', factor=Decimal('0.43444'), scope=3),
            dict(activity_key='flight_long_first', category='scope3_cat6_flight',
                 unit='km', factor=Decimal('0.59922'), scope=3),
            dict(activity_key='hotel_global_avg', category='scope3_cat6_hotel',
                 unit='room_night', factor=Decimal('20.8000'), scope=3),
            dict(activity_key='taxi_regular', category='scope3_cat6_ground',
                 unit='km', factor=Decimal('0.14876'), scope=3),
            dict(activity_key='rail_national', category='scope3_cat6_ground',
                 unit='km', factor=Decimal('0.03549'), scope=3),
        ]
        for f in factors:
            EmissionFactor.objects.get_or_create(
                activity_key=f['activity_key'],
                valid_from=date(2023, 1, 1),
                defaults=dict(
                    category=f['category'],
                    unit=f['unit'],
                    factor=f['factor'],
                    scope=f['scope'],
                    source='DEFRA 2023',
                ),
            )

        self.stdout.write(self.style.SUCCESS(
            f'Seed complete: tenant={tenant.slug}, facilities={len(facility_map)}, '
            f'factors={EmissionFactor.objects.count()}'
        ))
