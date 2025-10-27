from __future__ import annotations

from typing import Optional, Tuple

from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication, get_authorization_header

from .models import Usuario
from .utils import verify_auth_token


class SignedTokenAuthentication(BaseAuthentication):
    """
    Auth backend that understands the signed tokens issued by LoginView.
    This lets the rest of DRF share the same credentials as /auth/me.
    """

    keyword = b"bearer"

    def authenticate(self, request) -> Optional[Tuple[Usuario, str]]:
        header = get_authorization_header(request)
        if not header:
            return None

        parts = header.split()

        if parts[0].lower() != self.keyword:
            return None
        if len(parts) == 1:
            raise exceptions.AuthenticationFailed("Token incompleto.")
        if len(parts) > 2:
            raise exceptions.AuthenticationFailed("Cabecera Authorization invalida.")

        raw_token = parts[1].decode("utf-8").strip()
        if not raw_token:
            raise exceptions.AuthenticationFailed("Token vacio.")

        user_id = verify_auth_token(raw_token)
        if not user_id:
            raise exceptions.AuthenticationFailed("Token invalido o expirado.")

        try:
            user = Usuario.objects.get(pk=user_id)
        except Usuario.DoesNotExist as exc:
            raise exceptions.AuthenticationFailed("Usuario no encontrado.") from exc

        return (user, raw_token)

    def authenticate_header(self, request) -> str:
        return "Bearer"
