from django.contrib.auth.hashers import check_password as dj_check_password
from django.contrib.auth.hashers import make_password
from django.db import models


class Rol(models.Model):
    nombre = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.nombre


class Permiso(models.Model):
    nombre = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.nombre


class RolPermiso(models.Model):
    rol = models.ForeignKey(Rol, on_delete=models.CASCADE, related_name="rol_permisos")
    permiso = models.ForeignKey(Permiso, on_delete=models.CASCADE, related_name="permiso_roles")

    def __str__(self):
        return f"{self.rol.nombre} - {self.permiso.nombre}"


class Usuario(models.Model):
    username = models.CharField(max_length=100, unique=True)
    email = models.EmailField(max_length=150, unique=True)
    password = models.CharField(max_length=128)
    rol = models.ForeignKey(
        Rol,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="usuarios",
    )

    def __str__(self):
        return self.username

    def set_password(self, raw_password: str):
        self.password = make_password(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return dj_check_password(raw_password, self.password)

    @property
    def is_authenticated(self) -> bool:
        # Django REST Framework checks this attribute to identify real users
        return True

    @property
    def is_anonymous(self) -> bool:
        return False

    def save(self, *args, **kwargs):
        # Hash the password if it is provided in plain text
        if self.password and not self.password.startswith("pbkdf2_"):
            self.password = make_password(self.password)
        super().save(*args, **kwargs)

    def permisos_queryset(self):
        if not self.rol:
            return Permiso.objects.none()
        return Permiso.objects.filter(permiso_roles__rol=self.rol).distinct()
