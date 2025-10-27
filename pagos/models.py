from django.db import models
from usuarios.models import Usuario


class Factura(models.Model):
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='facturas'
    )
    stripe_invoice_id = models.CharField(max_length=120, unique=True)
    stripe_session_id = models.CharField(max_length=120)
    amount_total = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10, default='usd')
    status = models.CharField(max_length=50)
    hosted_invoice_url = models.URLField(blank=True, null=True)
    data = models.JSONField(default=dict, blank=True)
    stock_processed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Factura {self.stripe_invoice_id}'
