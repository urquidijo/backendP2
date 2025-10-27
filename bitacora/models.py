from django.db import models


class BitacoraEntry(models.Model):
    usuario = models.ForeignKey(
        "usuarios.Usuario",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="bitacora_entries",
    )
    accion = models.CharField(max_length=255)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creado_en"]
        verbose_name = "Bitacora"
        verbose_name_plural = "Bitacora"

    def __str__(self):
        usuario = self.usuario.username if self.usuario else "Anonimo"
        return f"{self.accion} por {usuario}"
