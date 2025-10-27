from django.contrib import admin

from .models import BitacoraEntry


@admin.register(BitacoraEntry)
class BitacoraEntryAdmin(admin.ModelAdmin):
    list_display = ("creado_en", "accion", "usuario", "ip_address")
    list_filter = ("accion",)
    search_fields = ("accion", "usuario__username", "ip_address")
    ordering = ("-creado_en",)
