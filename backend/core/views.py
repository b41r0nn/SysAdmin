from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from usuarios.models import Usuario
from inventario.models import Activo
from mantenimiento.models import OrdenMantenimiento

@login_required
def dashboard(request):
    hoy = timezone.now().date()
    ordenes_abiertas = OrdenMantenimiento.objects.filter(
        estado__in=["abierta", "en_proceso"]
    )
    ordenes_atrasadas = ordenes_abiertas.filter(
        plan__isnull=False,
        plan__proxima_ejecucion__lt=hoy,
    )
    context = {
        "total_usuarios": Usuario.objects.filter(estado="activo").count(),
        "total_activos": Activo.objects.count(),
        "activos_asignados": Activo.objects.filter(estado="asignado").count(),
        "activos_disponibles": Activo.objects.filter(estado="disponible").count(),
        "activos_baja": Activo.objects.filter(estado="dado_de_baja").count(),
        "ordenes_abiertas": ordenes_abiertas.count(),
        "ordenes_atrasadas": ordenes_atrasadas.count(),
    }
    return render(request, "core/dashboard.html", context)
