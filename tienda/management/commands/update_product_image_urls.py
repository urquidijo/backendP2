from django.core.management.base import BaseCommand
from django.db import transaction

from tienda.models import Producto
from tienda.s3_utils import _build_s3_base_url


class Command(BaseCommand):
    help = (
        "Actualiza productos antiguos para que usen URLs completas de S3 en el campo 'imagen'. "
        "Solo afecta registros cuyo valor actual no es un URL absoluto."
    )

    def handle(self, *args, **options):
        base_url = _build_s3_base_url()
        if not base_url:
            self.stderr.write(self.style.ERROR("No se pudo determinar la URL base de S3."))
            return

        updated = 0
        with transaction.atomic():
            productos = (
                Producto.objects.select_for_update()
                .filter(imagen__isnull=False)
                .exclude(imagen__exact="")
            )
            for producto in productos:
                if producto.imagen.startswith("http://") or producto.imagen.startswith("https://"):
                    continue
                producto.imagen = f"{base_url}/{producto.imagen.lstrip('/')}"
                producto.save(update_fields=["imagen"])
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Actualizacion completa. Productos modificados: {updated}."
            )
        )
