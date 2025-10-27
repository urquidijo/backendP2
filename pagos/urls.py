from django.urls import path
from .views import CheckoutSessionView, StripeWebhookView, FacturaListView

urlpatterns = [
    path('pagos/checkout/', CheckoutSessionView.as_view(), name='pagos-checkout'),
    path('pagos/webhook/', StripeWebhookView.as_view(), name='pagos-webhook'),
    path('pagos/facturas/', FacturaListView.as_view(), name='pagos-facturas'),
]
