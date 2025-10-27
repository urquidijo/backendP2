from django.urls import path

from .views import (
    ReportPromptView,
    SalesHistoryView,
    SalesPredictionView,
    TrainModelView,
)

urlpatterns = [
    path("analitica/reportes/", ReportPromptView.as_view(), name="analitica-reportes"),
    path("analitica/ventas/historicas/", SalesHistoryView.as_view(), name="analitica-historicas"),
    path("analitica/ventas/predicciones/", SalesPredictionView.as_view(), name="analitica-predicciones"),
    path("analitica/modelo/entrenar/", TrainModelView.as_view(), name="analitica-entrenar"),
]
