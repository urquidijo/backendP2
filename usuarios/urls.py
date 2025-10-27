from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    RolViewSet,
    PermisoViewSet,
    RolPermisoViewSet,
    UsuarioViewSet,
    LoginView,
    AuthMeView,
    LogoutView,
)

router = DefaultRouter()
router.register(r'rol', RolViewSet)
router.register(r'permiso', PermisoViewSet)
router.register(r'rolpermiso', RolPermisoViewSet)
router.register(r'usuario', UsuarioViewSet)

urlpatterns = [
    path('auth/login/', LoginView.as_view(), name='login'),
    path('auth/me/', AuthMeView.as_view(), name='auth-me'),
    path('auth/logout/', LogoutView.as_view(), name='auth-logout'),
    path('', include(router.urls)),
]
