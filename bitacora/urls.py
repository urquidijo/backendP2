from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import BitacoraEntryViewSet

router = DefaultRouter()
router.register(r"bitacora", BitacoraEntryViewSet, basename="bitacora")

urlpatterns = [
    path("", include(router.urls)),
]
