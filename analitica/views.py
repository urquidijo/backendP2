from django.http import HttpResponse
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from bitacora.utils import registrar_evento

from .services.prediction import get_historical_breakdown, get_predictions, train_model
from .services.prompt_parser import parse_prompt
from .services.report_builder import build_report
from .services.report_exporter import export_to_excel, export_to_pdf


class ReportPromptView(APIView):
    def post(self, request):
        prompt = request.data.get("prompt", "")
        format_override = request.data.get("format")
        channel = request.data.get("channel", "texto")

        if not prompt:
            return Response({"detail": "Debes ingresar un prompt."}, status=status.HTTP_400_BAD_REQUEST)

        parsed = parse_prompt(prompt, preferred_format=format_override)
        report = build_report(parsed.group_by, parsed.start_date, parsed.end_date)
        report["channel"] = channel
        report["prompt"] = prompt

        if parsed.report_format == "screen":
            serialized = {
                "metadata": {
                    "group_by": parsed.group_by,
                    "start_date": parsed.start_date.isoformat() if parsed.start_date else None,
                    "end_date": parsed.end_date.isoformat() if parsed.end_date else None,
                    "format": parsed.report_format,
                    "prompt": prompt,
                },
                "summary": [
                    {
                        "label": entry["label"],
                        "monto_total": float(entry["monto_total"]),
                        "cantidad": entry["cantidad"],
                    }
                    for entry in report["summary"]
                ],
                "rows": [
                    {
                        **row,
                        "monto_total": float(row["monto_total"]),
                    }
                    for row in report["rows"]
                ],
            }
            return Response(serialized, status=status.HTTP_200_OK)

        exporter = export_to_pdf if parsed.report_format == "pdf" else export_to_excel
        buffer = exporter(report)
        filename = (
            f"reporte_{parsed.start_date}_{parsed.end_date}."
            f"{'pdf' if parsed.report_format == 'pdf' else 'xlsx'}"
        )
        content_type = (
            "application/pdf"
            if parsed.report_format == "pdf"
            else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response = HttpResponse(buffer.getvalue(), content_type=content_type)
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        registrar_evento(
            request,
            f"DESCARGO REPORTE {parsed.report_format.upper()}",
        )
        return response


class SalesHistoryView(APIView):
    def get(self, _request):
        data = get_historical_breakdown()
        return Response(data, status=status.HTTP_200_OK)


class SalesPredictionView(APIView):
    def get(self, _request):
        data = get_predictions()
        return Response(data, status=status.HTTP_200_OK)


class TrainModelView(APIView):
    def post(self, _request):
        metadata = train_model()
        return Response(metadata, status=status.HTTP_201_CREATED)
