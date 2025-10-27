from rest_framework import viewsets, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from bitacora.utils import registrar_evento

from .models import Usuario, Rol, Permiso, RolPermiso
from .serializers import UsuarioSerializer, RolSerializer, PermisoSerializer, RolPermisoSerializer
from .utils import create_auth_token
from .authentication import SignedTokenAuthentication


class RolViewSet(viewsets.ModelViewSet):
    queryset = Rol.objects.all()
    serializer_class = RolSerializer


class PermisoViewSet(viewsets.ModelViewSet):
    queryset = Permiso.objects.all()
    serializer_class = PermisoSerializer


class RolPermisoViewSet(viewsets.ModelViewSet):
    queryset = RolPermiso.objects.all()
    serializer_class = RolPermisoSerializer


class UsuarioViewSet(viewsets.ModelViewSet):
    queryset = Usuario.objects.all()
    serializer_class = UsuarioSerializer

    def perform_create(self, serializer):
        usuario = serializer.save()
        registrar_evento(
            self.request,
            "CREO UN USUARIO",
        )

    def perform_update(self, serializer):
        usuario = serializer.save()
        registrar_evento(
            self.request,
            "ACTUALIZO UN USUARIO",
        )

    def perform_destroy(self, instance):
        instance.delete()
        registrar_evento(
            self.request,
            "ELIMINO UN USUARIO",
        )


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')

        if not username or not password:
            return Response(
                {'detail': 'Usuario y contrasena son requeridos'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            user = Usuario.objects.get(username=username)
        except Usuario.DoesNotExist:
            return Response(
                {'detail': 'Credenciales invalidas'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not user.check_password(password):
            return Response(
                {'detail': 'Credenciales invalidas'},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = UsuarioSerializer(user)
        token = create_auth_token(user.id)
        registrar_evento(
            request,
            "LOGIN",
        )
        return Response({'token': token, 'user': serializer.data}, status=status.HTTP_200_OK)


class AuthMeView(APIView):
    authentication_classes = [SignedTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UsuarioSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)


class LogoutView(APIView):
    authentication_classes = [SignedTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        registrar_evento(
            request,
            "LOGOUT",
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
