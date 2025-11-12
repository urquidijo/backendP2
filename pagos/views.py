import json
from decimal import Decimal
from typing import Optional, Tuple

import stripe
from django.conf import settings
from django.db.models import F, Q, Sum
from django.db.models.functions import Greatest
from django.utils import timezone
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from tienda.models import Producto, Carrito, ProductoDescuento
from usuarios.models import Usuario
from .models import Factura
from .serializers import FacturaSerializer

stripe.api_key = settings.STRIPE_SECRET_KEY


def _append_session_placeholder(url: str) -> str:
    if not url:
        return url
    if '{CHECKOUT_SESSION_ID}' in url:
        return url
    separator = '&' if '?' in url else '?'
    return f'{url}{separator}session_id={{CHECKOUT_SESSION_ID}}'


def _get_effective_price(producto: Producto) -> Tuple[Decimal, Optional[ProductoDescuento]]:
    ahora = timezone.now()
    try:
        descuento = (
            producto.descuentos.filter(fecha_inicio__lte=ahora)
            .filter(Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=ahora))
            .order_by("-fecha_inicio")
            .first()
        )
    except Exception:
        descuento = None

    if descuento:
        return descuento.precio_descuento, descuento

    return Decimal(producto.precio), None


class CheckoutSessionView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        items = request.data.get('items', [])
        usuario_id = request.data.get('usuarioId') or request.data.get('usuario_id')
        success_url = request.data.get('successUrl') or request.data.get('success_url')
        cancel_url = request.data.get('cancelUrl') or request.data.get('cancel_url')

        if not usuario_id:
            return Response({'detail': 'El identificador del usuario es requerido.'}, status=status.HTTP_400_BAD_REQUEST)

        if not items:
            return Response({'detail': 'Debes enviar al menos un producto.'}, status=status.HTTP_400_BAD_REQUEST)

        if not success_url:
            return Response({'detail': 'Debes proporcionar una URL de exito.'}, status=status.HTTP_400_BAD_REQUEST)

        line_items = []
        cart_items_metadata = []
        for item in items:
            product_id = item.get('productId') or item.get('product_id')
            quantity = int(item.get('quantity', 1))
            if not product_id or quantity < 1:
                continue

            try:
                product = Producto.objects.get(pk=product_id)
            except Producto.DoesNotExist:
                return Response({'detail': f'Producto {product_id} no encontrado.'}, status=status.HTTP_400_BAD_REQUEST)

            if product.stock < quantity:
                return Response(
                    {'detail': f'No hay stock suficiente para {product.nombre}.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            unit_price, active_discount = _get_effective_price(product)
            unit_amount = int((unit_price * 100).quantize(Decimal("1")))
            line_items.append({
                'quantity': quantity,
                'price_data': {
                    'currency': settings.STRIPE_CURRENCY,
                    'unit_amount': unit_amount,
                    'product_data': {
                        'name': product.nombre,
                        'description': product.descripcion or '',
                    },
                },
            })
            cart_items_metadata.append(
                {
                    'product_id': product_id,
                    'quantity': quantity,
                    'unit_price': str(unit_price),
                    'discount_id': active_discount.id if active_discount else None,
                    'discount_percentage': float(active_discount.porcentaje)
                    if active_discount
                    else None,
                }
            )

        if not line_items:
            return Response({'detail': 'No pudimos preparar los productos para Stripe.'}, status=status.HTTP_400_BAD_REQUEST)

        usuario = Usuario.objects.filter(pk=usuario_id).first()

        payment_methods = ['card']
        if settings.STRIPE_CURRENCY.lower() == 'usd':
            payment_methods.append('cashapp')

        metadata = {
            'usuario_id': str(usuario_id),
            'items': json.dumps(cart_items_metadata),
        }

        session_params = {
            'payment_method_types': payment_methods,
            'mode': 'payment',
            'line_items': line_items,
            'success_url': _append_session_placeholder(success_url),
            'cancel_url': cancel_url or success_url,
            'metadata': metadata,
            'invoice_creation': {
                'enabled': True,
                'invoice_data': {
                    'metadata': metadata,
                },
            },
        }

        if usuario:
            session_params['customer_email'] = usuario.email

        try:
            session = stripe.checkout.Session.create(**session_params)
        except stripe.error.StripeError as error:
            return Response({'detail': str(error)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({'url': session.url, 'sessionId': session.id})


class FacturaListView(ListAPIView):
    serializer_class = FacturaSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        usuario_id = self.request.query_params.get('usuario')
        queryset = Factura.objects.all()
        if usuario_id:
            queryset = queryset.filter(usuario_id=usuario_id)
        return queryset


class FacturaSummaryView(APIView):
    permission_classes = [AllowAny]

    def get(self, _request):
        queryset = Factura.objects.all()
        total_count = queryset.count()
        total_amount = queryset.aggregate(total=Sum('amount_total'))['total'] or Decimal('0')

        real_queryset = queryset.exclude(stripe_invoice_id__startswith='SYNTH-')
        real_count = real_queryset.count()
        real_amount = real_queryset.aggregate(total=Sum('amount_total'))['total'] or Decimal('0')

        return Response(
            {
                'count': total_count,
                'amount_total': float(total_amount),
                'real_count': real_count,
                'real_amount_total': float(real_amount),
            }
        )


class StripeWebhookView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        payload = request.body
        sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
        webhook_secret = settings.STRIPE_WEBHOOK_SECRET

        if webhook_secret:
            try:
                event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
            except ValueError:
                return Response({'detail': 'Payload invalido.'}, status=status.HTTP_400_BAD_REQUEST)
            except stripe.error.SignatureVerificationError:
                return Response({'detail': 'Firma invalida.'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            try:
                event = json.loads(payload.decode('utf-8'))
            except json.JSONDecodeError:
                return Response({'detail': 'No se pudo leer el evento.'}, status=status.HTTP_400_BAD_REQUEST)

        event_type = event.get('type')
        data_object = event.get('data', {}).get('object', {})

        if event_type == 'checkout.session.completed':
            self._handle_checkout_session(data_object)
        elif event_type in {'invoice.payment_succeeded', 'invoice.finalized'}:
            self._store_invoice(data_object)

        return Response({'status': 'ok'})

    def _handle_checkout_session(self, session):
        invoice_id = session.get('invoice')
        if not invoice_id:
            return

        try:
            invoice = stripe.Invoice.retrieve(invoice_id)
        except stripe.error.StripeError:
            return

        self._store_invoice(invoice, session)

    def _store_invoice(self, invoice, session=None):
        if not invoice.get('id'):
            return

        metadata = {}
        if session:
            metadata.update(session.get('metadata', {}))
        metadata.update(invoice.get('metadata', {}))

        usuario_id = metadata.get('usuario_id')
        usuario = Usuario.objects.filter(pk=usuario_id).first() if usuario_id else None
        items_metadata = metadata.get('items')
        cart_items = []
        if items_metadata:
            try:
                cart_items = json.loads(items_metadata)
            except (TypeError, json.JSONDecodeError):
                cart_items = []

        amount_raw = invoice.get('amount_paid') or invoice.get('amount_due') or 0
        amount_total = Decimal(amount_raw) / Decimal('100')

        defaults = {
            'usuario': usuario,
            'stripe_session_id': session.get('id') if session else invoice.get('id'),
            'amount_total': amount_total,
            'currency': invoice.get('currency', settings.STRIPE_CURRENCY),
            'status': invoice.get('status', 'pending'),
            'hosted_invoice_url': invoice.get('hosted_invoice_url'),
            'data': invoice,
        }

        factura, _created = Factura.objects.update_or_create(
            stripe_invoice_id=invoice['id'],
            defaults=defaults,
        )

        if cart_items and not factura.stock_processed:
            for item in cart_items:
                product_id = item.get('product_id')
                quantity = int(item.get('quantity', 0) or 0)
                if not product_id or quantity <= 0:
                    continue
                Producto.objects.filter(pk=product_id).update(
                    stock=Greatest(F('stock') - quantity, 0)
                )
            factura.stock_processed = True
            factura.save(update_fields=['stock_processed'])

        if usuario:
            Carrito.objects.filter(usuario=usuario, estado='pendiente').delete()
