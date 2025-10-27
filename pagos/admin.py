from django.contrib import admin
from .models import Factura


@admin.register(Factura)
class FacturaAdmin(admin.ModelAdmin):
    list_display = ('stripe_invoice_id', 'usuario', 'amount_total', 'status', 'created_at')
    search_fields = ('stripe_invoice_id', 'usuario__username')
    list_filter = ('status',)
