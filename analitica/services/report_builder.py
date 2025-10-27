from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional

from pagos.models import Factura


def _normalize_amount(value):
    if value is None:
        return Decimal("0")
    if isinstance(value, (int, float)):
        return Decimal(value) / (Decimal("100") if value > 1000 else Decimal("1"))
    if isinstance(value, str):
        try:
            return Decimal(value)
        except Exception:  # pragma: no cover
            return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal("0")


def _expand_invoice_lines(factura: Factura):
    data = factura.data or {}
    lines = data.get("lines", {}).get("data", [])
    if not lines:
        return [
            {
                "producto": "Venta general",
                "cantidad": 1,
                "total": factura.amount_total,
            }
        ]

    expanded = []
    for line in lines:
        description = (
            line.get("description")
            or line.get("price", {})
            .get("product_data", {})
            .get("name", "Producto sin nombre")
        )
        cantidad = int(line.get("quantity", 1))
        amount = line.get("amount_total") or line.get("amount_subtotal") or line.get("amount")
        expanded.append(
            {
                "producto": description,
                "cantidad": cantidad,
                "total": _normalize_amount(amount),
            }
        )
    return expanded


def build_report(group_by: str, start_date: Optional[date], end_date: Optional[date]):
    queryset = Factura.objects.select_related("usuario").all()
    if start_date:
        queryset = queryset.filter(created_at__date__gte=start_date)
    if end_date:
        queryset = queryset.filter(created_at__date__lte=end_date)

    summary: Dict[str, Dict[str, Decimal | int | str]] = defaultdict(
        lambda: {"label": "", "monto_total": Decimal("0"), "cantidad": 0}
    )
    rows: List[Dict[str, str]] = []

    for factura in queryset:
        cliente = factura.usuario.username if factura.usuario else "Sin cliente"
        for line in _expand_invoice_lines(factura):
            if group_by == "producto":
                key = line["producto"]
            elif group_by == "cliente":
                key = cliente
            elif group_by == "categoria":
                key = line["producto"]
            else:
                key = factura.created_at.strftime("%Y-%m")

            summary_entry = summary[key]
            summary_entry["label"] = key
            summary_entry["monto_total"] += line["total"]
            summary_entry["cantidad"] += int(line["cantidad"])

            rows.append(
                {
                    "factura": factura.stripe_invoice_id,
                    "cliente": cliente,
                    "producto": line["producto"],
                    "cantidad": int(line["cantidad"]),
                    "monto_total": line["total"],
                    "fecha": factura.created_at.strftime("%Y-%m-%d"),
                }
            )

    summary_list = sorted(summary.values(), key=lambda item: item["monto_total"], reverse=True)

    return {
        "rows": rows,
        "summary": summary_list,
        "start_date": start_date.isoformat() if start_date else None,
        "end_date": end_date.isoformat() if end_date else None,
        "group_by": group_by,
    }
