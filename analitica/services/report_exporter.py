from io import BytesIO
from typing import Dict, List

from openpyxl import Workbook
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def export_to_pdf(report_data: Dict):
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(40, height - 50, "Reporte dinamico de ventas")

    pdf.setFont("Helvetica", 10)
    pdf.drawString(40, height - 70, f"Periodo: {report_data.get('start_date')} - {report_data.get('end_date')}")
    pdf.drawString(40, height - 85, f"Agrupado por: {report_data.get('group_by')}")

    y = height - 120
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(40, y, "Resumen")
    y -= 20
    pdf.setFont("Helvetica", 10)
    for entry in report_data.get("summary", [])[:15]:
        pdf.drawString(
            40,
            y,
            f"{entry['label']}: {float(entry['monto_total']):.2f} ({entry['cantidad']} unidades)",
        )
        y -= 15
        if y < 80:
            pdf.showPage()
            y = height - 80

    pdf.showPage()
    pdf.save()
    buffer.seek(0)
    return buffer


def export_to_excel(report_data: Dict):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Reporte"

    headers = ["Factura", "Cliente", "Producto", "Cantidad", "Monto", "Fecha"]
    sheet.append(headers)

    for row in report_data.get("rows", []):
        sheet.append(
            [
                row["factura"],
                row["cliente"],
                row["producto"],
                row["cantidad"],
                float(row["monto_total"]),
                row["fecha"],
            ]
        )

    summary_sheet = workbook.create_sheet("Resumen")
    summary_sheet.append(["Etiqueta", "Monto total", "Cantidad"])
    for entry in report_data.get("summary", []):
        summary_sheet.append(
            [entry["label"], float(entry["monto_total"]), entry["cantidad"]]
        )

    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return buffer
