from decimal import Decimal
from datetime import timedelta

from django.db import models
from django.utils import timezone

from usuarios.models import Usuario  # usamos tu modelo de usuario existente


class Categoria(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    descripcion = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.nombre


class Producto(models.Model):
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True, null=True)
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.IntegerField()
    low_stock_threshold = models.PositiveIntegerField(default=0)
    categoria = models.ForeignKey(Categoria, on_delete=models.SET_NULL, null=True, related_name="productos")
    imagen = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return self.nombre


class ProductoDescuento(models.Model):
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name="descuentos")
    porcentaje = models.DecimalField(max_digits=5, decimal_places=2)
    fecha_inicio = models.DateTimeField()
    fecha_fin = models.DateTimeField(blank=True, null=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-fecha_inicio"]

    def __str__(self):
        return f"Descuento {self.porcentaje}% - {self.producto.nombre}"

    @property
    def esta_activo(self) -> bool:
        ahora = timezone.now()
        if self.fecha_inicio and self.fecha_inicio > ahora:
            return False
        if self.fecha_fin and self.fecha_fin < ahora:
            return False
        return True

    @property
    def precio_descuento(self) -> Decimal:
        descuento = (self.porcentaje or Decimal("0")) / Decimal("100")
        precio = self.producto.precio or Decimal("0")
        precio_final = precio * (Decimal("1") - descuento)
        return precio_final.quantize(Decimal("0.01"))


class Carrito(models.Model):
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name="carritos")
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    estado = models.CharField(max_length=50, default="pendiente")
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Carrito #{self.id} - {self.usuario.username}"

    @property
    def esta_expirado(self) -> bool:
        return self.actualizado_en < timezone.now() - timedelta(hours=1)


class CarritoDetalle(models.Model):
    carrito = models.ForeignKey(Carrito, on_delete=models.CASCADE, related_name="detalles")
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE)
    cantidad = models.IntegerField()
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.producto.nombre} x {self.cantidad}"
