import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

import joblib
import numpy as np
import pandas as pd
from django.conf import settings
from django.db.models import Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone
from pagos.models import Factura
from pagos.services.synthetic_invoices import TARGET_MONTHS, ensure_synthetic_invoices
from sklearn.ensemble import RandomForestRegressor
from tienda.models import Categoria, Producto

MODEL_DIR = Path(settings.ANALITICA_MODEL_DIR)
MODEL_DIR.mkdir(parents=True, exist_ok=True)
MODEL_PATH = MODEL_DIR / "random_forest.pkl"
MODEL_META_PATH = MODEL_DIR / "model_meta.json"


def _convert_amount(value) -> float:
    if value is None:
        return 0.0
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    return numeric / 100 if numeric > 1000 else numeric


def _monthly_sales_dataframe() -> pd.DataFrame:
    queryset = Factura.objects.annotate(month=TruncMonth("created_at")).values("month").annotate(
        total=Sum("amount_total")
    )
    df = pd.DataFrame(list(queryset))
    if df.empty:
        return df

    df["month"] = pd.to_datetime(df["month"]).dt.tz_localize(None).dt.to_period("M")
    df = (
        df.groupby("month", as_index=False)["total"]
        .sum()
        .sort_values("month")
        .reset_index(drop=True)
    )
    return df


def _aggregate_monthly_sales():
    ensure_synthetic_invoices(months=TARGET_MONTHS)

    df = _monthly_sales_dataframe()
    if df.empty:
        today = pd.Timestamp(timezone.now().date()).normalize()
        synthetic_dates = pd.date_range(end=today, periods=TARGET_MONTHS, freq="M")
        fallback_records = []
        for index, stamp in enumerate(synthetic_dates, start=1):
            fallback_records.append(
                {
                    "month_index": index,
                    "label": stamp.strftime("%Y-%m"),
                    "total": float(1000 + np.random.randint(0, 700)),
                }
            )
        return pd.DataFrame(fallback_records), fallback_records

    latest_period = df["month"].max()
    earliest_period = df["month"].min()
    desired_start = latest_period - (TARGET_MONTHS - 1)
    start_period = earliest_period if earliest_period <= desired_start else desired_start
    period_range = pd.period_range(start=start_period, end=latest_period, freq="M")

    reindexed = df.set_index("month").reindex(period_range, fill_value=0).rename_axis("month").reset_index()
    reindexed["label"] = reindexed["month"].dt.strftime("%Y-%m")
    reindexed["month_index"] = range(1, len(reindexed) + 1)
    reindexed["total"] = reindexed["total"].astype(float)

    data = reindexed[["month_index", "label", "total"]].to_dict("records")
    return reindexed[["month_index", "label", "total"]], data


def _load_metadata():
    if MODEL_META_PATH.exists():
        return json.loads(MODEL_META_PATH.read_text())
    return {}


def _save_metadata(metadata: Dict):
    MODEL_META_PATH.write_text(json.dumps(metadata, indent=2))


def _build_metadata_snapshot(df: pd.DataFrame, rows: List[Dict]) -> Dict:
    invoice_count = Factura.objects.count()
    product_count = Producto.objects.count()
    category_count = Categoria.objects.count()
    period_from = rows[0]["label"] if rows else None
    period_to = rows[-1]["label"] if rows else None

    return {
        "samples": int(len(rows)),
        "invoice_count": int(invoice_count),
        "product_count": int(product_count),
        "category_count": int(category_count),
        "period_from": period_from,
        "period_to": period_to,
    }


def train_model():
    df, rows = _aggregate_monthly_sales()

    model = RandomForestRegressor(n_estimators=200, random_state=42)
    model.fit(df[["month_index"]], df["total"])
    joblib.dump(model, MODEL_PATH)

    metadata = {
        "trained_at": timezone.now().isoformat(),
        **_build_metadata_snapshot(df, rows),
    }
    _save_metadata(metadata)
    return metadata


def _load_or_train_model():
    metadata = _load_metadata()
    if not MODEL_PATH.exists():
        metadata = train_model()

    model = joblib.load(MODEL_PATH)
    df, rows = _aggregate_monthly_sales()

    metadata = {
        **metadata,
        **_build_metadata_snapshot(df, rows),
    }
    return model, metadata, df, rows


def _extract_factura_items(factura):
    metadata = {}
    if isinstance(factura.data, dict):
        metadata = factura.data.get("metadata", {}) or {}

    items_payload = metadata.get("items")
    cart_items: List[Dict] = []
    if items_payload:
        try:
            cart_items = json.loads(items_payload)
        except (TypeError, json.JSONDecodeError):
            cart_items = []

    line_items = []
    if isinstance(factura.data, dict):
        line_items = (factura.data.get("lines") or {}).get("data", []) or []

    detailed_items = []
    for index, item in enumerate(cart_items):
        product_id = int(item.get("product_id") or 0)
        quantity = int(item.get("quantity") or 0)
        amount = None
        if index < len(line_items):
            amount = _convert_amount(
                line_items[index].get("amount_total") or line_items[index].get("amount")
            )
        detailed_items.append(
            {
                "product_id": product_id,
                "quantity": quantity,
                "amount": amount,
                "fallback": line_items[index] if index < len(line_items) else None,
            }
        )
    return detailed_items, line_items


def _collect_factura_data():
    facturas = Factura.objects.select_related("usuario").all()
    product_ids = set()
    factura_items: List[Tuple[Factura, List[Dict], List[Dict]]] = []

    for factura in facturas:
        items, fallback_lines = _extract_factura_items(factura)
        for item in items:
            if item["product_id"]:
                product_ids.add(item["product_id"])
        factura_items.append((factura, items, fallback_lines))

    products_lookup = {
        product.id: product
        for product in Producto.objects.filter(id__in=product_ids).select_related("categoria")
    }
    return factura_items, products_lookup


def _aggregate_category_monthly_sales(rows: List[Dict]):
    factura_items, products_lookup = _collect_factura_data()
    month_index_map = {row["label"]: row["month_index"] for row in rows}

    monthly_category_totals: Dict[Tuple[str, str], float] = defaultdict(float)
    category_totals: Dict[str, float] = defaultdict(float)

    for factura, items, fallback_lines in factura_items:
        label = factura.created_at.strftime("%Y-%m")
        month_index = month_index_map.get(label)
        if month_index is None:
            continue

        if not items and fallback_lines:
            for line in fallback_lines:
                amount = _convert_amount(line.get("amount_total") or line.get("amount"))
                monthly_category_totals[("Sin categoria", label)] += amount
                category_totals["Sin categoria"] += amount
            continue

        for index, item in enumerate(items):
            product = products_lookup.get(item["product_id"])
            amount = item["amount"]
            fallback_line = item.get("fallback") if item.get("fallback") else (
                fallback_lines[index] if index < len(fallback_lines) else None
            )

            if product:
                if amount is None:
                    amount = float(product.precio) * item["quantity"]
                category_label = product.categoria.nombre if product.categoria else "Sin categoria"
            else:
                if amount is None and fallback_line:
                    amount = _convert_amount(
                        fallback_line.get("amount_total") or fallback_line.get("amount")
                    )
                category_label = "Sin categoria"

            amount = float(amount or 0)
            monthly_category_totals[(category_label, label)] += amount
            category_totals[category_label] += amount

    records = [
        {
            "category": category,
            "label": label,
            "month_index": month_index_map[label],
            "total": total,
        }
        for (category, label), total in monthly_category_totals.items()
    ]

    df = (
        pd.DataFrame(records)
        if records
        else pd.DataFrame(columns=["category", "label", "month_index", "total"])
    )
    return df, category_totals


def get_historical_breakdown():
    _, rows = _aggregate_monthly_sales()
    monthly_totals = rows

    product_totals: Dict[str, float] = defaultdict(float)
    category_totals: Dict[str, float] = defaultdict(float)
    customer_totals: Dict[str, float] = defaultdict(float)

    factura_items, products_lookup = _collect_factura_data()

    for factura, items, fallback_lines in factura_items:
        cliente = factura.usuario.username if factura.usuario else "Sin cliente"
        customer_totals[cliente] += float(factura.amount_total or 0)

        if not items and fallback_lines:
            for line in fallback_lines:
                description = (
                    line.get("description")
                    or line.get("price", {}).get("product_data", {}).get("name", "Producto sin nombre")
                )
                amount = _convert_amount(line.get("amount_total") or line.get("amount"))
                product_totals[description] += amount
                category_totals["Sin categoria"] += amount
            continue

        for index, item in enumerate(items):
            product = products_lookup.get(item["product_id"])
            amount = item["amount"]
            fallback_line = item.get("fallback") if item.get("fallback") else (
                fallback_lines[index] if index < len(fallback_lines) else None
            )

            if product:
                if amount is None:
                    amount = float(product.precio) * item["quantity"]
                product_label = product.nombre
                category_label = product.categoria.nombre if product.categoria else "Sin categoria"
            else:
                product_label = (
                    (fallback_line or {}).get("description") or "Producto sin asociar"
                )
                if amount is None and fallback_line:
                    amount = _convert_amount(
                        fallback_line.get("amount_total") or fallback_line.get("amount")
                    )
                category_label = "Sin categoria"

            amount = float(amount or 0)
            product_totals[product_label] += amount
            category_totals[category_label] += amount

    product_summary = sorted(
        ({"label": label, "total": total} for label, total in product_totals.items()),
        key=lambda item: item["total"],
        reverse=True,
    )
    customer_summary = sorted(
        ({"label": label, "total": total} for label, total in customer_totals.items()),
        key=lambda item: item["total"],
        reverse=True,
    )
    category_summary = sorted(
        ({"label": label, "total": total} for label, total in category_totals.items()),
        key=lambda item: item["total"],
        reverse=True,
    )

    return {
        "monthly_totals": monthly_totals,
        "by_product": product_summary[:20],
        "by_customer": customer_summary[:8],
        "by_category": category_summary,
    }


def get_predictions(months: int = 6):
    model, metadata, df, rows = _load_or_train_model()
    last_label = rows[-1]["label"]
    last_date = pd.to_datetime(f"{last_label}-01")

    start_index = int(df["month_index"].max())
    future_indices = np.arange(start_index + 1, start_index + months + 1).reshape(-1, 1)
    predicted = model.predict(future_indices)

    future_dates = pd.date_range(
        start=last_date + pd.offsets.MonthEnd(1), periods=months, freq="M"
    )

    predictions = []
    for date_stamp, value in zip(future_dates, predicted):
        predictions.append(
            {"label": date_stamp.strftime("%Y-%m"), "total": round(float(value), 2)}
        )

    metadata = {
        **metadata,
        "generated_at": timezone.now().isoformat(),
    }

    category_df, category_totals = _aggregate_category_monthly_sales(rows)
    overall_total = sum(category_totals.values()) or 1.0
    sorted_categories = sorted(
        category_totals.items(), key=lambda item: item[1], reverse=True
    )

    category_predictions: List[Dict] = []
    for category_label, total in sorted_categories:
        historical_subset = category_df[category_df["category"] == category_label].sort_values(
            "month_index"
        )
        history_series = [
            {"label": row["label"], "total": round(float(row["total"]), 2)}
            for _, row in historical_subset.iterrows()
        ]

        if len(historical_subset) >= 3:
            category_model = RandomForestRegressor(n_estimators=150, random_state=42)
            category_model.fit(
                historical_subset[["month_index"]],
                historical_subset["total"],
            )
            category_pred = category_model.predict(future_indices)
            forecast_series = [
                {"label": date_stamp.strftime("%Y-%m"), "total": round(float(value), 2)}
                for date_stamp, value in zip(future_dates, category_pred)
            ]
        else:
            share = total / overall_total
            forecast_series = [
                {
                    "label": date_stamp.strftime("%Y-%m"),
                    "total": round(float(value) * share, 2),
                }
                for date_stamp, value in zip(future_dates, predicted)
            ]

        category_predictions.append(
            {
                "category": category_label,
                "share": round((total / overall_total) * 100, 2),
                "historical": history_series,
                "predictions": forecast_series,
            }
        )

    return {
        "predictions": predictions,
        "metadata": metadata,
        "by_category": category_predictions,
    }
