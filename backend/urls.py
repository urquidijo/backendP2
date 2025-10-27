from django.contrib import admin
from django.urls import path, include
from pagos.views import StripeWebhookView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('usuarios.urls')),
    path('api/', include('tienda.urls')),
    path('api/', include('pagos.urls')),
    path('api/', include('analitica.urls')),
    path('api/', include('bitacora.urls')),
    path('webhooks/stripe/', StripeWebhookView.as_view(), name='stripe-webhook-direct'),
]
