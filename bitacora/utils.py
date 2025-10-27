from __future__ import annotations

from typing import Any, Optional

from .models import BitacoraEntry


def _get_client_ip(request) -> Optional[str]:
    if not request:
        return None
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip_list = [ip.strip() for ip in x_forwarded_for.split(",") if ip.strip()]
        if ip_list:
            return ip_list[0]
    return request.META.get("REMOTE_ADDR")


def registrar_evento(
    request,
    accion: str,
    *,
    usuario_override: Optional[Any] = None,
) -> BitacoraEntry:
    """
    Guarda una entrada en la bitácora con la información disponible.
    """

    usuario = None
    if usuario_override is not None:
        usuario = usuario_override
    elif request and hasattr(request, "user"):
        user_obj = request.user
        if getattr(user_obj, "is_authenticated", False):
            usuario = user_obj

    return BitacoraEntry.objects.create(
        usuario=usuario,
        accion=accion,
        ip_address=_get_client_ip(request),
    )
