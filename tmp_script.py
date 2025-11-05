from tienda.models import Categoria
print([ (c.id, c.nombre) for c in Categoria.objects.all()[:5] ])

