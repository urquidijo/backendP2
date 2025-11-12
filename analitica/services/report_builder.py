from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List, Optional, Set, Tuple

from pagos.models import Factura


@dataclass
class ReportOptions:
    include_invoice_counts: bool = False
    include_date_span: bool = False
    order_by_date: bool = True


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
                "categoria": "Sin categoria",
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
        categoria = (
            line.get("category")
            or line.get("metadata", {}).get("category")
            or "Sin categoria"
        )
        expanded.append(
            {
                "producto": description,
                "cantidad": cantidad,
                "total": _normalize_amount(amount),
                "categoria": categoria,
            }
        )
    return expanded


def _group_key(group_by: str, factura: Factura, line: Dict[str, str]) -> Tuple[str, Optional[datetime]]:
    if group_by == "producto":
        return line["producto"], factura.created_at
    if group_by == "cliente":
        cliente = factura.usuario.username if factura.usuario else "Sin cliente"
        return cliente, factura.created_at
    if group_by == "categoria":
        return line["categoria"], factura.created_at

    label = factura.created_at.strftime("%Y-%m")
    month_start = factura.created_at.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return label, month_start


def build_report(
    group_by: str,
    start_date: Optional[date],
    end_date: Optional[date],
    *,
    include_invoice_counts: bool = False,
    include_date_span: bool = False,
    order_by_date: bool = True,
):
    queryset = Factura.objects.select_related("usuario").all().order_by("created_at")
    if start_date:
        queryset = queryset.filter(created_at__date__gte=start_date)
    if end_date:
        queryset = queryset.filter(created_at__date__lte=end_date)

    summary: Dict[str, Dict[str, object]] = defaultdict(
        lambda: {
            "label": "",
            "monto_total": Decimal("0"),
            "cantidad": 0,
            "first_date": None,
            "last_date": None,
            "invoice_ids": set(),
        }
    )
    rows: List[Dict[str, object]] = []

    for factura in queryset:
        cliente = factura.usuario.username if factura.usuario else "Sin cliente"
        for line in _expand_invoice_lines(factura):
            key, key_date = _group_key(group_by, factura, line)
            summary_entry = summary[key]
            summary_entry["label"] = key
            summary_entry["monto_total"] += line["total"]
            summary_entry["cantidad"] += int(line["cantidad"])

            factura_date = factura.created_at.date()
            if summary_entry["first_date"] is None or factura_date < summary_entry["first_date"]:
                summary_entry["first_date"] = factura_date
            if summary_entry["last_date"] is None or factura_date > summary_entry["last_date"]:
                summary_entry["last_date"] = factura_date

            invoice_ids: Set[int] = summary_entry["invoice_ids"]  # type: ignore[assignment]
            if factura.id not in invoice_ids:
                invoice_ids.add(factura.id)

            rows.append(
                {
                    "factura": factura.stripe_invoice_id,
                    "cliente": cliente,
                    "producto": line["producto"],
                    "categoria": line["categoria"],
                    "cantidad": int(line["cantidad"]),
                    "monto_total": float(line["total"]),
                    "fecha": factura.created_at.strftime("%Y-%m-%d"),
                }
            )

    rows.sort(key=lambda row: row["fecha"])

    summary_list: List[Dict[str, object]] = []
    summary_fields: List[Tuple[str, str]] = [
        ("label", "Etiqueta"),
        ("monto_total", "Monto total"),
        ("cantidad", "Unidades"),
    ]
    if include_invoice_counts:
        summary_fields.append(("compras", "Compras"))
    if include_date_span:
        summary_fields.append(("fecha_primera", "Primera compra"))
        summary_fields.append(("fecha_ultima", "Ultima compra"))

    for entry in summary.values():
        record = {
            "label": entry["label"],
            "monto_total": float(entry["monto_total"]),
            "cantidad": entry["cantidad"],
        }
        if include_invoice_counts:
            record["compras"] = len(entry["invoice_ids"])  # type: ignore[index]
        if include_date_span and entry["first_date"]:
            record["fecha_primera"] = entry["first_date"].isoformat()
            record["fecha_ultima"] = entry["last_date"].isoformat()
        summary_list.append(record)

    def _parse_label_to_date(label: str) -> Optional[datetime]:
        try:
            return datetime.strptime(label, "%Y-%m")
        except ValueError:
            return None

    def _parse_iso(value: object) -> Optional[datetime]:
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return None
        return None

    if order_by_date and summary_list:
        summary_list.sort(
            key=lambda item: (
                _parse_label_to_date(str(item["label"])) or _parse_iso(item.get("fecha_primera")) or datetime.max,
                _parse_iso(item.get("fecha_primera")) or datetime.max,
            )
        )
    else:
        summary_list.sort(key=lambda item: item["monto_total"], reverse=True)

    return {
        "rows": rows,
        "summary": summary_list,
        "summary_fields": [{"key": key, "title": title} for key, title in summary_fields],
        "start_date": start_date.isoformat() if start_date else None,
        "end_date": end_date.isoformat() if end_date else None,
        "group_by": group_by,
    }
