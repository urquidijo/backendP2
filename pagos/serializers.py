from rest_framework import serializers
from .models import Factura


class FacturaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Factura
        fields = [
            'id',
            'usuario',
            'stripe_invoice_id',
            'stripe_session_id',
            'amount_total',
            'currency',
            'status',
            'hosted_invoice_url',
            'created_at',
        ]
