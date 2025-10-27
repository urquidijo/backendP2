from rest_framework import serializers

from .models import Permiso, Rol, RolPermiso, Usuario


class RolSerializer(serializers.ModelSerializer):
    class Meta:
        model = Rol
        fields = ["id", "nombre"]


class PermisoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permiso
        fields = ["id", "nombre"]


class RolPermisoSerializer(serializers.ModelSerializer):
    rol_nombre = serializers.CharField(source="rol.nombre", read_only=True)
    permiso_nombre = serializers.CharField(source="permiso.nombre", read_only=True)

    class Meta:
        model = RolPermiso
        fields = ["id", "rol", "permiso", "rol_nombre", "permiso_nombre"]


class UsuarioSerializer(serializers.ModelSerializer):
    rol_nombre = serializers.CharField(source="rol.nombre", read_only=True)
    permisos = serializers.SerializerMethodField()

    class Meta:
        model = Usuario
        fields = ["id", "username", "email", "password", "rol", "rol_nombre", "permisos"]
        extra_kwargs = {
            "password": {"write_only": True},
            "rol": {"required": False, "allow_null": True},
        }

    def get_permisos(self, obj: Usuario):
        return list(obj.permisos_queryset().values_list("nombre", flat=True))

    def _get_default_role(self) -> Rol:
        default_role = Rol.objects.filter(nombre__iexact="Cliente").first()
        if not default_role:
            raise serializers.ValidationError(
                {"rol": "No existe un rol 'Cliente'. Crea uno antes de registrar usuarios."}
            )
        return default_role

    def create(self, validated_data):
        role = validated_data.get("rol") or self._get_default_role()
        user = Usuario(
            username=validated_data["username"],
            email=validated_data["email"],
            rol=role,
        )
        user.set_password(validated_data["password"])
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance
