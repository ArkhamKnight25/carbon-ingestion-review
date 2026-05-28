from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    TenantViewSet, FacilityViewSet, PlantCodeMappingViewSet,
    EmissionFactorViewSet, BatchViewSet, EmissionRecordViewSet,
    dashboard_stats,
)

router = DefaultRouter()
router.register(r'tenants', TenantViewSet, basename='tenant')
router.register(r'facilities', FacilityViewSet, basename='facility')
router.register(r'plant-codes', PlantCodeMappingViewSet, basename='plantcode')
router.register(r'factors', EmissionFactorViewSet, basename='factor')
router.register(r'batches', BatchViewSet, basename='batch')
router.register(r'records', EmissionRecordViewSet, basename='record')

urlpatterns = [
    path('', include(router.urls)),
    path('dashboard/', dashboard_stats),
]
