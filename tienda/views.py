from decimal import Decimal

from django.db.models import F, Q
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from bitacora.permissions import IsAdministrador
from bitacora.utils import registrar_evento

from .models import Categoria, Producto, ProductoDescuento, Carrito, CarritoDetalle
from .serializers import (
    CategoriaSerializer,
    ProductoSerializer,
    ProductoDescuentoSerializer,
    CarritoSerializer,
    CarritoDetalleSerializer,
)
from .s3_utils import S3UploadError, upload_product_image


class CategoriaViewSet(viewsets.ModelViewSet):
    queryset = Categoria.objects.all()
    serializer_class = CategoriaSerializer


class ProductoViewSet(viewsets.ModelViewSet):
    queryset = Producto.objects.all()
    serializer_class = ProductoSerializer
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def _prepare_payload(self, request):
        data = request.data.copy()

        imagen_file = request.FILES.get("imagen_archivo") or request.FILES.get("imagen")
        if imagen_file:
            try:
                imagen_url = upload_product_image(imagen_file, filename=imagen_file.name)
            except S3UploadError as exc:
                raise ValidationError({"imagen": [str(exc)]})
            data["imagen"] = imagen_url
            # Remove the helper field so the serializer does not complain about an unknown key.
            if "imagen_archivo" in data:
                data.pop("imagen_archivo")
        else:
            # Make sure we do not leak the helper field when no upload took place.
            data.pop("imagen_archivo", None)

        if data.get("imagen") == "":
            data["imagen"] = None

        categoria_val = data.get("categoria_id")
        if categoria_val in {"", "null", "None"}:
            data["categoria_id"] = None

        return data

    def create(self, request, *args, **kwargs):
        data = self._prepare_payload(request)
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        data = self._prepare_payload(request)
        serializer = self.get_serializer(instance, data=data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)

    def partial_update(self, request, *args, **kwargs):
        """
        Handle PATCH requests with the same preprocessing logic used for PUT.
        Ensures new product images uploaded via multipart FormData are persisted.
        """
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    def perform_create(self, serializer):
        serializer.save()
        registrar_evento(
            self.request,
            "CREO UN PRODUCTO",
        )

    def perform_update(self, serializer):
        serializer.save()
        registrar_evento(
            self.request,
            "ACTUALIZO UN PRODUCTO",
        )

    def perform_destroy(self, instance):
        instance.delete()
        registrar_evento(
            self.request,
            "ELIMINO UN PRODUCTO",
        )

    @action(
        detail=False,
        methods=["get"],
        permission_classes=[IsAuthenticated, IsAdministrador],
        url_path="low-stock",
    )
    def low_stock(self, request):
        queryset = self.get_queryset().filter(
            low_stock_threshold__gt=0,
            stock__lte=F("low_stock_threshold"),
        )
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class ProductoDescuentoViewSet(viewsets.ModelViewSet):
    queryset = ProductoDescuento.objects.select_related("producto", "producto__categoria")
    serializer_class = ProductoDescuentoSerializer
    permission_classes = [IsAuthenticated, IsAdministrador]

    def get_permissions(self):
        if self.action in {"activos"}:
            return [permissions.AllowAny()]
        return super().get_permissions()

    def get_queryset(self):
        queryset = super().get_queryset()
        activos_param = self.request.query_params.get("activos")
        if activos_param and activos_param.lower() in {"1", "true", "yes"}:
            return self._filter_activos(queryset)
        return queryset

    def _filter_activos(self, queryset):
        ahora = timezone.now()
        return queryset.filter(fecha_inicio__lte=ahora).filter(Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=ahora))

    def create(self, request, *args, **kwargs):
        product_ids = request.data.get("productos") or request.data.get("product_ids")
        if isinstance(product_ids, list) and product_ids:
            created = []
            errores = []
            base_data = request.data.copy()
            base_data.pop("productos", None)
            base_data.pop("product_ids", None)

            for product_id in product_ids:
                data = {**base_data, "producto_id": product_id}
                serializer = self.get_serializer(data=data)
                if serializer.is_valid():
                    self.perform_create(serializer)
                    created.append(serializer.data)
                else:
                    errores.append({"producto": product_id, "errores": serializer.errors})

            status_code = status.HTTP_201_CREATED if not errores else status.HTTP_207_MULTI_STATUS
            return Response({"creados": created, "errores": errores}, status=status_code)

        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        instance = serializer.save()
        registrar_evento(
            self.request,
            f"CREO DESCUENTO {instance.porcentaje}% PARA {instance.producto.nombre}",
        )

    def perform_update(self, serializer):
        instance = serializer.save()
        registrar_evento(
            self.request,
            f"ACTUALIZO DESCUENTO {instance.porcentaje}% PARA {instance.producto.nombre}",
        )

    def perform_destroy(self, instance):
        nombre = instance.producto.nombre
        instance.delete()
        registrar_evento(
            self.request,
            f"ELIMINO DESCUENTO DE {nombre}",
        )

    @action(detail=False, methods=["get"], permission_classes=[permissions.AllowAny], url_path="activos")
    def activos(self, request):
        queryset = self._filter_activos(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class CarritoViewSet(viewsets.ModelViewSet):
    queryset = Carrito.objects.all()
    serializer_class = CarritoSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Carrito.objects.filter(usuario=self.request.user).order_by("-actualizado_en")

    def perform_create(self, serializer):
        serializer.save(usuario=self.request.user)

    def _obtener_precio_actual(self, producto: Producto) -> Decimal:
        ahora = timezone.now()
        descuento = (
            producto.descuentos.filter(fecha_inicio__lte=ahora)
            .filter(Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=ahora))
            .order_by("-fecha_inicio")
            .first()
        )
        if descuento:
            return descuento.precio_descuento
        return producto.precio

    def _get_or_create_cart(self, user):
        cart = (
            Carrito.objects.filter(usuario=user, estado="pendiente")
            .order_by("-actualizado_en")
            .first()
        )
        if cart and cart.esta_expirado:
            cart.detalles.all().delete()
            cart.delete()
            cart = None
        if not cart:
            cart = Carrito.objects.create(usuario=user)
        return cart

    @action(detail=False, methods=["get", "post"], permission_classes=[IsAuthenticated], url_path="actual")
    def actual(self, request):
        cart = self._get_or_create_cart(request.user)

        if request.method == "GET":
            serializer = self.get_serializer(cart)
            return Response(serializer.data)

        items = request.data.get("items", [])
        cart.detalles.all().delete()
        total = Decimal("0")

        for item in items:
            product_id = item.get("productId") or item.get("product_id")
            quantity = int(item.get("quantity") or 0)
            if not product_id or quantity <= 0:
                continue

            try:
                product = Producto.objects.get(pk=product_id)
            except Producto.DoesNotExist:
                continue

            unit_price = self._obtener_precio_actual(product)
            subtotal = (unit_price or Decimal("0")) * Decimal(str(quantity))
            CarritoDetalle.objects.create(
                carrito=cart,
                producto=product,
                cantidad=quantity,
                subtotal=subtotal.quantize(Decimal("0.01")),
            )
            total += subtotal

        cart.total = total.quantize(Decimal("0.01"))
        cart.estado = "pendiente"
        cart.save(update_fields=["total", "estado", "actualizado_en"])

        serializer = self.get_serializer(cart)
        return Response(serializer.data)


class CarritoDetalleViewSet(viewsets.ModelViewSet):
    queryset = CarritoDetalle.objects.all()
    serializer_class = CarritoDetalleSerializer
