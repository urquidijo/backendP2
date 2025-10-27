from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("tienda", "0002_producto_low_stock_threshold"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProductoDescuento",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("porcentaje", models.DecimalField(decimal_places=2, max_digits=5)),
                ("fecha_inicio", models.DateTimeField()),
                ("fecha_fin", models.DateTimeField(blank=True, null=True)),
                ("creado_en", models.DateTimeField(auto_now_add=True)),
                ("actualizado_en", models.DateTimeField(auto_now=True)),
                (
                    "producto",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="descuentos",
                        to="tienda.producto",
                    ),
                ),
            ],
            options={
                "ordering": ["-fecha_inicio"],
            },
        ),
    ]
