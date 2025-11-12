from django.core.management.base import BaseCommand
from pagos.models import Factura
from pagos.services.synthetic_invoices import rebuild_invoice_dataset

DATASET_START_YEAR = 2023
DATASET_START_MONTH = 1
TARGET_DATASET_INVOICES = 500
MONTHLY_TARGET_RANGE = (80000.0, 100000.0)
MONTHLY_OVERRIDE_RANGES = {
    1: (55000.0, 70000.0),   # Enero con menor actividad
    11: (90000.0, 110000.0),  # Black Friday / temporada alta
    12: (100000.0, 130000.0),  # Navidad
}


class Command(BaseCommand):
    help = (
        "Elimina todas las facturas y genera un dataset sintético que cubre desde 2023 hasta el mes actual "
        "utilizando todos los usuarios, productos y categorías disponibles."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Muestra las acciones que se ejecutarían sin modificar la base de datos.",
        )
        parser.add_argument(
            "--seed",
            type=int,
            default=42,
            help="Semilla para la generación pseudoaleatoria (por defecto 42).",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        seed = options["seed"]

        existing = Factura.objects.count()

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"(dry-run) Se eliminarían {existing} facturas antes de generar el nuevo dataset."
                )
            )
        else:
            deleted, _ = Factura.objects.all().delete()
            self.stdout.write(
                self.style.WARNING(f"Se eliminaron {deleted} facturas existentes antes de recrear el dataset.")
            )

        summaries = rebuild_invoice_dataset(
            start_year=DATASET_START_YEAR,
            start_month=DATASET_START_MONTH,
            target_invoice_total=TARGET_DATASET_INVOICES,
            monthly_target_range=MONTHLY_TARGET_RANGE,
            monthly_amount_overrides=MONTHLY_OVERRIDE_RANGES,
            seed=seed,
            dry_run=dry_run,
        )

        if not summaries:
            self.stdout.write(self.style.SUCCESS("No fue necesario generar facturas adicionales."))
            return

        total_invoices = sum(summary["created_invoices"] for summary in summaries)
        total_amount = sum(summary["total"] for summary in summaries)

        label = "(dry-run) Dataset planificado" if dry_run else "Dataset recreado"
        self.stdout.write(
            self.style.SUCCESS(
                f"{label}: {total_invoices} facturas (~{total_amount:,.2f} USD) entre {summaries[0]['label']} "
                f"y {summaries[-1]['label']}."
            )
        )
