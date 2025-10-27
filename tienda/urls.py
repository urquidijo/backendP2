from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CategoriaViewSet,
    ProductoViewSet,
    ProductoDescuentoViewSet,
    CarritoViewSet,
    CarritoDetalleViewSet,
)

router = DefaultRouter()
router.register(r'categorias', CategoriaViewSet)
router.register(r'productos', ProductoViewSet)
router.register(r'descuentos', ProductoDescuentoViewSet, basename='descuentos')
router.register(r'carritos', CarritoViewSet)
router.register(r'carrito-detalle', CarritoDetalleViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
