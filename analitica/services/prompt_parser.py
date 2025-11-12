import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

MONTHS = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}


@dataclass
class PromptData:
    prompt: str
    group_by: str
    report_format: str
    start_date: Optional[date]
    end_date: Optional[date]
    order_by_date: bool = True
    include_purchase_counts: bool = False
    include_date_span: bool = False


def _parse_explicit_dates(prompt: str):
    pattern = r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})"
    matches = re.findall(pattern, prompt)
    if len(matches) >= 2:
        start = _to_date(matches[0])
        end = _to_date(matches[1])
        return start, end
    return None, None


def _parse_month_reference(prompt: str):
    month_match = re.search(r"mes de (\w+)", prompt)
    if not month_match:
        return None, None

    month_label = month_match.group(1)
    month_number = MONTHS.get(month_label.lower())
    if not month_number:
        return None, None

    today = date.today()
    start = date(today.year, month_number, 1)
    end = (start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    return start, end


def _to_date(raw: str):
    day, month, year = re.split(r"[/-]", raw)
    year = int(year)
    if year < 100:
        year += 2000
    return date(int(year), int(month), int(day))


def _detect_group(prompt: str):
    if "producto" in prompt:
        return "producto"
    if "cliente" in prompt or "usuario" in prompt:
        return "cliente"
    if "categoria" in prompt:
        return "categoria"
    return "mes"


def _detect_format(prompt: str, fallback: Optional[str] = None):
    if "pdf" in prompt:
        return "pdf"
    if "excel" in prompt or "xlsx" in prompt:
        return "excel"
    if "pantalla" in prompt:
        return "screen"
    return fallback or "screen"


def parse_prompt(prompt: str, preferred_format: Optional[str] = None) -> PromptData:
    normalized = prompt.lower()
    start_date, end_date = _parse_explicit_dates(normalized)

    if not start_date:
        month_start, month_end = _parse_month_reference(normalized)
        if month_start:
            start_date, end_date = month_start, month_end

    if not start_date:
        end_date = date.today()
        start_date = end_date - timedelta(days=30)

    report_format = _detect_format(normalized, preferred_format)
    group_by = _detect_group(normalized)

    include_purchase_counts = any(
        phrase in normalized
        for phrase in (
            "cantidad de compras",
            "numero de compras",
            "número de compras",
            "compras que realiz",
        )
    )
    include_date_span = any(
        phrase in normalized
        for phrase in (
            "rango de fechas",
            "rango de compra",
            "fechas en las que",
        )
    )

    return PromptData(
        prompt=prompt,
        group_by=group_by,
        report_format=report_format,
        start_date=start_date,
        end_date=end_date,
        order_by_date=True,
        include_purchase_counts=include_purchase_counts,
        include_date_span=include_date_span,
    )
