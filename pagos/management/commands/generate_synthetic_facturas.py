from django.core.management.base import BaseCommand, CommandError

from pagos.models import Factura
from pagos.services.synthetic_invoices import SYNTHETIC_PREFIX, TARGET_MONTHS, ensure_synthetic_invoices


class Command(BaseCommand):
    help = "Genera facturas sintéticas en Stripe (modo local) para completar meses faltantes."

    def add_arguments(self, parser):
        parser.add_argument(
            "--months",
            type=int,
            default=TARGET_MONTHS,
            help=f"Cantidad de meses recientes a garantizar (por defecto {TARGET_MONTHS}).",
        )
        parser.add_argument(
            "--min-invoices",
            type=int,
            default=4,
            dest="min_invoices",
            help="Número mínimo de facturas sintéticas por mes (>=1).",
        )
        parser.add_argument(
            "--max-invoices",
            type=int,
            default=12,
            dest="max_invoices",
            help="Número máximo de facturas sintéticas por mes (>= min).",
        )
        parser.add_argument(
            "--base-amount",
            type=float,
            default=900.0,
            dest="base_amount",
            help="Monto base promedio para el cálculo de ventas mensuales.",
        )
        parser.add_argument(
            "--seed",
            type=int,
            default=None,
            help="Semilla para reproducibilidad.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Muestra los resultados sin escribir en la base de datos.",
        )
        parser.add_argument(
            "--refresh",
            action="store_true",
            help="Elimina facturas sintéticas previas antes de generar nuevas (ignoradas en --dry-run).",
        )

    def handle(self, *args, **options):
        months = options["months"]
        min_invoices = options["min_invoices"]
        max_invoices = options["max_invoices"]
        base_amount = options["base_amount"]
        seed = options.get("seed")
        dry_run = options["dry_run"]
        refresh = options["refresh"]

        if months <= 0:
            raise CommandError("El parámetro --months debe ser mayor que cero.")
        if min_invoices < 1:
            raise CommandError("El parámetro --min-invoices debe ser al menos 1.")
        if max_invoices < min_invoices:
            raise CommandError("--max-invoices debe ser mayor o igual a --min-invoices.")
        if base_amount <= 0:
            raise CommandError("--base-amount debe ser positivo.")

        try:
            if refresh:
                queryset = Factura.objects.filter(
                    stripe_invoice_id__startswith=SYNTHETIC_PREFIX
                )
                if dry_run:
                    count = queryset.count()
                    if count:
                        self.stdout.write(
                            self.style.WARNING(
                                f"(dry-run) Se eliminarían {count} facturas sintéticas existentes antes de recrearlas."
                            )
                        )
                else:
                    deleted, _ = queryset.delete()
                    if deleted:
                        self.stdout.write(
                            self.style.WARNING(
                                f"Se eliminaron {deleted} facturas sintéticas existentes antes de regenerar."
                            )
                        )

            summaries = ensure_synthetic_invoices(
                months=months,
                min_invoices=min_invoices,
                max_invoices=max_invoices,
                base_amount=base_amount,
                seed=seed,
                dry_run=dry_run,
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        if not summaries:
            self.stdout.write(self.style.SUCCESS("No se requirió crear facturas sintéticas."))
            return

        label = "Previsualización" if dry_run else "Creado"
        for summary in summaries:
            self.stdout.write(
                f"{label}: {summary['created_invoices']} facturas para {summary['label']} "
                f"(total aproximado: {summary['total']:.2f})"
            )

        if dry_run:
            self.stdout.write(self.style.WARNING("Ejecutado en modo --dry-run; no se realizaron cambios."))
        else:
            self.stdout.write(self.style.SUCCESS("Facturas sintéticas generadas correctamente."))
