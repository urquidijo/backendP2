import json
import math
import random
import uuid
from collections import defaultdict, deque
from datetime import date, datetime, time as time_cls, timedelta, timezone as dt_timezone
from decimal import Decimal, ROUND_HALF_UP
from itertools import cycle
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from django.db import transaction
from django.utils import timezone

from pagos.models import Factura
from tienda.models import Categoria, Producto
from usuarios.models import Usuario

SYNTHETIC_PREFIX = "SYNTH"
TARGET_MONTHS = 24
MIN_ORDER_TOTAL = Decimal("35.00")
MAX_ITEMS_PER_INVOICE = 5


def _month_starts(months: int, end_date: Optional[date] = None) -> List[date]:
    if months <= 0:
        return []

    if end_date is None:
        end_date = timezone.now().date()
    end_date = end_date.replace(day=1)

    year, month = end_date.year, end_date.month
    starts: List[date] = []
    for _ in range(months):
        starts.append(date(year, month, 1))
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    starts.reverse()
    return starts


def _advance_month(month_start: date) -> date:
    if month_start.month == 12:
        return date(month_start.year + 1, 1, 1)
    return date(month_start.year, month_start.month + 1, 1)


def _month_boundaries(month_start: date) -> Tuple[datetime, datetime]:
    start_naive = datetime.combine(month_start, time_cls.min)
    end_naive = datetime.combine(_advance_month(month_start), time_cls.min)
    current_tz = timezone.get_current_timezone()
    start_aware = timezone.make_aware(start_naive, current_tz) if timezone.is_naive(start_naive) else start_naive
    end_aware = timezone.make_aware(end_naive, current_tz) if timezone.is_naive(end_naive) else end_naive
    return start_aware, end_aware


def _random_created_at(month_start: date, month_end: date) -> datetime:
    total_days = (month_end - month_start).days
    if total_days <= 0:
        total_days = 1
    day_offset = random.randrange(total_days)
    random_date = month_start + timedelta(days=day_offset)
    random_time = time_cls(
        hour=random.randint(8, 20),
        minute=random.randint(0, 59),
        second=random.randint(0, 59),
    )
    naive = datetime.combine(random_date, random_time)
    return naive.replace(tzinfo=dt_timezone.utc)


def _load_entities() -> Tuple[Sequence[Usuario], Sequence[Producto], Dict[Optional[int], List[Producto]], List[int]]:
    usuarios = list(Usuario.objects.order_by("id"))
    productos = list(Producto.objects.select_related("categoria").order_by("id"))

    if not productos:
        raise ValueError(
            "No existen productos cargados en la base de datos. Registre productos antes de generar facturas sintéticas."
        )
    if not usuarios:
        raise ValueError(
            "No existen usuarios registrados en la base de datos. Registre usuarios antes de generar facturas sintéticas."
        )

    category_map: Dict[Optional[int], List[Producto]] = defaultdict(list)
    for producto in productos:
        category_map[producto.categoria_id].append(producto)

    category_ids = [
        categoria.id
        for categoria in Categoria.objects.order_by("id")
        if category_map.get(categoria.id)
    ]
    if not category_ids:
        category_ids = [key for key, value in category_map.items() if key is not None and value]

    return usuarios, productos, category_map, category_ids


def _safe_quantity(producto: Producto) -> int:
    if producto.stock and producto.stock > 0:
        return max(1, min(5, producto.stock))
    return random.randint(1, 4)


def _build_invoice_payload(
    *,
    primary_product: Producto,
    productos: Sequence[Producto],
    target_total: Decimal,
) -> Tuple[Decimal, List[Dict], List[Dict]]:
    items: List[Dict] = []
    lines: List[Dict] = []
    running_total = Decimal("0.00")

    product_pool = deque(productos)
    random.shuffle(product_pool)

    for _ in range(MAX_ITEMS_PER_INVOICE):
        producto = primary_product if not items else (product_pool[0] if product_pool else primary_product)
        if product_pool:
            product_pool.rotate(-1)

        cantidad = _safe_quantity(producto)
        line_total = (producto.precio or Decimal("0.00")) * Decimal(cantidad)
        line_total = line_total.quantize(Decimal("0.01"))

        if line_total <= 0:
            continue

        running_total += line_total
        items.append(
            {
                "product_id": producto.id,
                "quantity": cantidad,
                "total": line_total,
            }
        )
        lines.append(
            {
                "description": producto.nombre,
                "amount_total": int((line_total * 100).to_integral_value()),
                "quantity": cantidad,
                "category": producto.categoria.nombre if producto.categoria else "Sin categoria",
            }
        )

        if running_total >= target_total and len(items) >= 1:
            break

        if running_total >= target_total * Decimal("1.35"):
            break

        primary_product = producto

    if running_total < MIN_ORDER_TOTAL and items:
        diff = MIN_ORDER_TOTAL - running_total
        running_total += diff
        items[-1]["total"] = items[-1]["total"] + diff
        lines[-1]["amount_total"] = int((items[-1]["total"] * 100).to_integral_value())

    return running_total, items, lines


def ensure_synthetic_invoices(
    months: int = TARGET_MONTHS,
    *,
    min_invoices: int = 4,
    max_invoices: int = 12,
    base_amount: float = 900.0,
    seed: Optional[int] = None,
    dry_run: bool = False,
) -> List[Dict]:
    """
    Genera facturas sintéticas persistentes utilizando usuarios y productos reales.
    Devuelve un resumen por mes con la cantidad de facturas creadas y su total.
    """
    if months <= 0:
        return []
    if min_invoices < 1:
        raise ValueError("min_invoices must be greater than 0")
    if max_invoices < min_invoices:
        raise ValueError("max_invoices must be >= min_invoices")

    if seed is not None:
        random.seed(seed)
        np.random.seed(seed)

    usuarios, productos, category_map, category_ids = _load_entities()
    month_starts = _month_starts(months)
    if not month_starts:
        return []

    user_cycle = cycle(usuarios)
    product_cycle = cycle(productos)

    min_per_month_for_users = math.ceil(len(usuarios) / len(month_starts))
    min_per_month_for_products = math.ceil(len(productos) / len(month_starts))
    required_min = max(
        min_invoices,
        min_per_month_for_users,
        min_per_month_for_products,
        len(category_ids),
    )
    if required_min > max_invoices:
        max_invoices = required_min

    summaries: List[Dict] = []

    for index, month_start in enumerate(month_starts):
        start_dt, end_dt = _month_boundaries(month_start)
        month_end = end_dt.date()
        label = month_start.strftime("%Y-%m")
        month_qs = Factura.objects.filter(
            created_at__gte=start_dt,
            created_at__lt=end_dt,
        )

        if month_qs.exists():
            continue

        invoice_count = max(required_min, random.randint(min_invoices, max_invoices))

        seasonal = math.sin(((month_start.month - 1) / 12) * 2 * math.pi) * base_amount * 0.3
        growth = index * (base_amount * 0.025)
        noise = random.gauss(0, base_amount * 0.12)
        monthly_total = base_amount + seasonal + growth + noise
        monthly_total = max(base_amount * 0.45, monthly_total)

        monthly_total_decimal = Decimal(monthly_total).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

        summary = {
            "label": label,
            "created_invoices": invoice_count,
            "total": float(monthly_total_decimal),
        }
        summaries.append(summary)

        if dry_run:
            continue

        metadata_base = {
            "origin": "synthetic",
            "label": label,
            "notes": "Generated for analytics backfill",
        }

        with transaction.atomic():
            created_total = Decimal("0.00")
            remaining_target = monthly_total_decimal
            category_queue = deque(category_ids)
            random.shuffle(category_queue)

            for invoice_number in range(invoice_count):
                remaining_invoices = invoice_count - invoice_number
                if category_queue:
                    category_id = category_queue.popleft()
                    product_choices = category_map.get(category_id) or productos
                    primary_product = random.choice(product_choices)
                else:
                    primary_product = next(product_cycle)
                usuario = next(user_cycle)

                target_total = (
                    remaining_target / remaining_invoices if remaining_invoices else Decimal("0.00")
                )
                target_total = max(MIN_ORDER_TOTAL, target_total.quantize(Decimal("0.01")))

                order_total, items, line_payload = _build_invoice_payload(
                    primary_product=primary_product,
                    productos=productos,
                    target_total=target_total,
                )
                order_total = order_total.quantize(Decimal("0.01"))

                items_for_metadata = [
                    {
                        "product_id": item["product_id"],
                        "quantity": item["quantity"],
                        "amount": float(item["total"]),
                    }
                    for item in items
                ]

                metadata = {
                    **metadata_base,
                    "usuario_id": usuario.id,
                    "usuario_username": usuario.username,
                    "items": json.dumps(items_for_metadata),
                }

                factura = Factura.objects.create(
                    usuario=usuario,
                    stripe_invoice_id=f"{SYNTHETIC_PREFIX}-{label}-{uuid.uuid4().hex[:10].upper()}",
                    stripe_session_id=f"{SYNTHETIC_PREFIX}-SESSION-{uuid.uuid4().hex[:10].upper()}",
                    amount_total=order_total,
                    currency="usd",
                    status="paid",
                    hosted_invoice_url="",
                    data={
                        "metadata": metadata,
                        "lines": {"data": line_payload},
                    },
                    stock_processed=True,
                )

                created_at = _random_created_at(month_start, month_end)
                Factura.objects.filter(pk=factura.pk).update(created_at=created_at)

                created_total += order_total
                remaining_target = max(Decimal("0.00"), remaining_target - order_total)

            summary["total"] = float(created_total.quantize(Decimal("0.01")))

    return summaries


__all__ = ["ensure_synthetic_invoices", "TARGET_MONTHS", "SYNTHETIC_PREFIX"]
