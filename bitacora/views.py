from rest_framework import mixins, viewsets

from .models import BitacoraEntry
from .permissions import IsAdministrador
from .serializers import BitacoraEntrySerializer


class BitacoraEntryViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = BitacoraEntry.objects.select_related("usuario", "usuario__rol").all()
    serializer_class = BitacoraEntrySerializer
    permission_classes = [IsAdministrador]
