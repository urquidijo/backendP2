from rest_framework import serializers

from .models import BitacoraEntry


class BitacoraEntrySerializer(serializers.ModelSerializer):
    usuario_username = serializers.CharField(source="usuario.username", read_only=True)

    class Meta:
        model = BitacoraEntry
        fields = [
            "id",
            "usuario",
            "usuario_username",
            "accion",
            "ip_address",
            "creado_en",
        ]
        read_only_fields = fields
