from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers

from .models import Categoria, Producto, ProductoDescuento, Carrito, CarritoDetalle


class ProductoDescuentoLiteSerializer(serializers.ModelSerializer):
    precio_original = serializers.SerializerMethodField()
    precio_con_descuento = serializers.SerializerMethodField()
    esta_activo = serializers.SerializerMethodField()

    class Meta:
        model = ProductoDescuento
        fields = [
            "id",
            "porcentaje",
            "fecha_inicio",
            "fecha_fin",
            "precio_original",
            "precio_con_descuento",
            "esta_activo",
        ]

    def get_precio_original(self, obj):
        return obj.producto.precio

    def get_precio_con_descuento(self, obj):
        return obj.precio_descuento

    def get_esta_activo(self, obj):
        return obj.esta_activo


class CategoriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Categoria
        fields = '__all__'


class ProductoSerializer(serializers.ModelSerializer):
    categoria = CategoriaSerializer(read_only=True)
    categoria_id = serializers.PrimaryKeyRelatedField(
        queryset=Categoria.objects.all(), source='categoria', write_only=True
    )
    active_discount = serializers.SerializerMethodField()

    class Meta:
        model = Producto
        fields = [
            'id',
            'nombre',
            'descripcion',
            'precio',
            'stock',
            'low_stock_threshold',
            'categoria',
            'categoria_id',
            'imagen',
            'active_discount',
        ]

    def get_active_discount(self, obj):
        ahora = timezone.now()
        try:
            descuento = (
                obj.descuentos.filter(fecha_inicio__lte=ahora)
                .filter(Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=ahora))
                .order_by("-fecha_inicio")
                .first()
            )
        except Exception:
            return None

        if not descuento:
            return None
        return ProductoDescuentoLiteSerializer(descuento).data


class ProductoDescuentoSerializer(ProductoDescuentoLiteSerializer):
    producto = ProductoSerializer(read_only=True)
    producto_id = serializers.PrimaryKeyRelatedField(
        queryset=Producto.objects.all(), source="producto", write_only=True
    )

    class Meta(ProductoDescuentoLiteSerializer.Meta):
        fields = ProductoDescuentoLiteSerializer.Meta.fields + ["producto", "producto_id"]

    def validate_porcentaje(self, value):
        if value <= 0 or value >= 100:
            raise serializers.ValidationError("El porcentaje debe ser mayor a 0 y menor a 100.")
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        producto = attrs.get("producto") or getattr(self.instance, "producto", None)
        fecha_inicio = attrs.get("fecha_inicio") or getattr(self.instance, "fecha_inicio", None)
        fecha_fin = attrs.get("fecha_fin") if "fecha_fin" in attrs else getattr(self.instance, "fecha_fin", None)

        if fecha_fin and fecha_inicio and fecha_fin <= fecha_inicio:
            raise serializers.ValidationError(
                {"fecha_fin": "La fecha de finalizacion debe ser posterior a la fecha de inicio."}
            )

        if producto and fecha_inicio:
            margen = timedelta(days=3650)
            nuevo_fin = fecha_fin or (fecha_inicio + margen)

            queryset = ProductoDescuento.objects.filter(producto=producto)
            if self.instance:
                queryset = queryset.exclude(pk=self.instance.pk)

            for existente in queryset:
                existente_fin = existente.fecha_fin or (existente.fecha_inicio + margen)
                if existente.fecha_inicio <= nuevo_fin and fecha_inicio <= existente_fin:
                    raise serializers.ValidationError(
                        "Ya existe un descuento que se superpone con las fechas seleccionadas para este producto."
                    )

        return attrs


class CarritoDetalleSerializer(serializers.ModelSerializer):
    producto = ProductoSerializer(read_only=True)
    producto_id = serializers.PrimaryKeyRelatedField(
        queryset=Producto.objects.all(), source='producto', write_only=True
    )

    class Meta:
        model = CarritoDetalle
        fields = ['id', 'producto', 'producto_id', 'cantidad', 'subtotal']


class CarritoSerializer(serializers.ModelSerializer):
    detalles = CarritoDetalleSerializer(many=True, read_only=True)
    actualizado_en = serializers.DateTimeField(read_only=True)
    expires_at = serializers.SerializerMethodField()
    total = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    estado = serializers.CharField(read_only=True)

    class Meta:
        model = Carrito
        fields = ['id', 'total', 'estado', 'actualizado_en', 'expires_at', 'detalles']
        read_only_fields = fields

    def get_expires_at(self, obj):
        expiration = obj.actualizado_en + timedelta(hours=1)
        return expiration.isoformat()
