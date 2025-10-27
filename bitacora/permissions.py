from rest_framework.permissions import BasePermission


class IsAdministrador(BasePermission):
    """
    Permite acceso únicamente a usuarios con rol 'Administrador'.
    """

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return False
        rol = getattr(user, "rol", None)
        if not rol:
            return False
        return rol.nombre.lower() == "administrador"
