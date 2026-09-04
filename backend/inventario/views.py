from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
import weasyprint

from .forms import (
    ActivoForm, CatalogoModeloForm, AsignacionForm,
    DevolucionForm, TrasladoForm, SubirActaForm,
)
from .models import Activo, Asignacion, CatalogoModelo, Movimiento, ActaAsignacion


# ── Lista ──────────────────────────────────────────────────────────────────────

@login_required
def lista_activos(request):
    qs = Activo.objects.all()

    tipo = request.GET.get("tipo", "")
    estado = request.GET.get("estado", "")
    q = request.GET.get("q", "").strip()

    if tipo:
        qs = qs.filter(tipo_dispositivo=tipo)
    if estado:
        qs = qs.filter(estado=estado)
    if q:
        qs = qs.filter(
            Q(serial__icontains=q)
            | Q(marca__icontains=q)
            | Q(modelo__icontains=q)
            | Q(imei__icontains=q)
        )

    from .models import ESTADOS, TIPOS
    stats = {
        "total": Activo.objects.count(),
        "asignados": Activo.objects.filter(estado="asignado").count(),
        "disponibles": Activo.objects.filter(estado="disponible").count(),
        "baja": Activo.objects.filter(estado="dado_de_baja").count(),
    }

    ctx = {
        "activos": qs,
        "tipos": TIPOS,
        "estados": ESTADOS,
        "filtro_tipo": tipo,
        "filtro_estado": estado,
        "filtro_q": q,
        "stats": stats,
    }

    if request.headers.get("HX-Request"):
        return render(request, "inventario/partials/tabla.html", ctx)

    return render(request, "inventario/lista.html", ctx)


# ── Detalle ────────────────────────────────────────────────────────────────────

@login_required
def detalle_activo(request, pk):
    activo = get_object_or_404(Activo, pk=pk)
    asignacion_activa = activo.asignaciones.filter(activa=True).first()
    movimientos = activo.movimientos.select_related("usuario_destino").order_by("-fecha", "-fecha_creacion")
    actas = []
    for a in activo.asignaciones.all():
        if hasattr(a, "acta"):
            actas.append(a.acta)

    ctx = {
        "activo": activo,
        "asignacion_activa": asignacion_activa,
        "movimientos": movimientos,
        "actas": actas,
    }
    return render(request, "inventario/detalle.html", ctx)


# ── Crear ──────────────────────────────────────────────────────────────────────

@login_required
def crear_activo(request):
    if request.method == "POST":
        form = ActivoForm(request.POST, request.FILES)
        if form.is_valid():
            activo = form.save()
            messages.success(request, f"Activo «{activo}» creado correctamente.")
            return redirect("inventario:detalle", pk=activo.pk)
        else:
            messages.error(request, "Corrige los errores del formulario.")
    else:
        form = ActivoForm()

    return render(request, "inventario/form.html", {"form": form, "titulo": "Nuevo Activo"})


# ── Editar ─────────────────────────────────────────────────────────────────────

@login_required
def editar_activo(request, pk):
    activo = get_object_or_404(Activo, pk=pk)
    if request.method == "POST":
        form = ActivoForm(request.POST, request.FILES, instance=activo)
        if form.is_valid():
            form.save()
            messages.success(request, f"Activo «{activo}» actualizado.")
            return redirect("inventario:detalle", pk=activo.pk)
        else:
            messages.error(request, "Corrige los errores del formulario.")
    else:
        form = ActivoForm(instance=activo)

    return render(request, "inventario/form.html", {"form": form, "titulo": "Editar Activo", "activo": activo})


# ── Baja (toggle) ──────────────────────────────────────────────────────────────

@login_required
def toggle_baja_activo(request, pk):
    activo = get_object_or_404(Activo, pk=pk)
    if request.method == "POST":
        if activo.estado == "dado_de_baja":
            activo.estado = "disponible"
            messages.warning(request, f"Activo «{activo}» reactivado.")
        else:
            if activo.asignaciones.filter(activa=True).exists():
                messages.error(request, "No se puede dar de baja un activo asignado. Devuélvelo primero.")
                return redirect("inventario:detalle", pk=activo.pk)
            activo.estado = "dado_de_baja"
            messages.success(request, f"Activo «{activo}» dado de baja.")
        activo.save()
    return redirect("inventario:detalle", pk=activo.pk)


# ── Movimientos ───────────────────────────────────────────────────────────────

@login_required
def asignar_activo(request, pk):
    activo = get_object_or_404(Activo, pk=pk)
    if activo.estado != "disponible":
        messages.error(request, "Solo se pueden asignar activos disponibles.")
        return redirect("inventario:detalle", pk=activo.pk)
        
    if request.method == "POST":
        form = AsignacionForm(request.POST)
        if form.is_valid():
            asignacion = form.save(commit=False)
            asignacion.activo = activo
            asignacion.fecha_asignacion = timezone.now().date()
            asignacion.save()
            
            Movimiento.objects.create(
                activo=activo,
                tipo="asignacion",
                fecha=timezone.now().date(),
                descripcion=f"Asignado a {asignacion.usuario.nombre_completo}. {asignacion.observaciones or ''}",
                realizado_por=request.user.username if request.user.is_authenticated else "Sistema",
                usuario_destino=asignacion.usuario
            )
            
            ActaAsignacion.objects.create(asignacion=asignacion)
            
            activo.estado = "asignado"
            activo.save()
            
            messages.success(request, f"Activo asignado a {asignacion.usuario.nombre_completo}.")
            return redirect("inventario:detalle", pk=activo.pk)
    else:
        form = AsignacionForm()
        
    return render(request, "inventario/asignacion_form.html", {
        "form": form, "titulo": "Asignar Activo", "activo": activo, "accion": "Asignar"
    })

@login_required
def devolver_activo(request, pk):
    activo = get_object_or_404(Activo, pk=pk)
    asignacion = activo.asignaciones.filter(activa=True).first()
    
    if not asignacion:
        messages.error(request, "El activo no tiene una asignación activa.")
        return redirect("inventario:detalle", pk=activo.pk)
        
    if request.method == "POST":
        form = DevolucionForm(request.POST)
        if form.is_valid():
            observaciones = form.cleaned_data["observaciones"]
            
            asignacion.activa = False
            asignacion.fecha_devolucion = timezone.now().date()
            if observaciones:
                asignacion.observaciones = (asignacion.observaciones or "") + f"\n[Devolución]: {observaciones}"
            asignacion.save()
            
            Movimiento.objects.create(
                activo=activo,
                tipo="devolucion",
                fecha=timezone.now().date(),
                descripcion=f"Devuelto por {asignacion.usuario.nombre_completo}. {observaciones}",
                realizado_por=request.user.username if request.user.is_authenticated else "Sistema"
            )
            
            activo.estado = "disponible"
            activo.save()
            
            messages.success(request, "Activo devuelto correctamente.")
            return redirect("inventario:detalle", pk=activo.pk)
    else:
        form = DevolucionForm()
        
    return render(request, "inventario/asignacion_form.html", {
        "form": form, "titulo": "Devolver Activo", "activo": activo, "accion": "Devolver"
    })

@login_required
def trasladar_activo(request, pk):
    activo = get_object_or_404(Activo, pk=pk)
    asignacion_actual = activo.asignaciones.filter(activa=True).first()
    
    if not asignacion_actual:
        messages.error(request, "El activo no está asignado actualmente.")
        return redirect("inventario:detalle", pk=activo.pk)
        
    if request.method == "POST":
        form = TrasladoForm(request.POST)
        if form.is_valid():
            usuario_destino = form.cleaned_data["usuario_destino"]
            observaciones = form.cleaned_data["observaciones"]
            
            if usuario_destino == asignacion_actual.usuario:
                messages.error(request, "El usuario destino debe ser diferente al actual.")
                return render(request, "inventario/asignacion_form.html", {
                    "form": form, "titulo": "Trasladar Activo", "activo": activo, "accion": "Trasladar"
                })
            
            # 1. Cerrar asignación actual
            asignacion_actual.activa = False
            asignacion_actual.fecha_devolucion = timezone.now().date()
            if observaciones:
                asignacion_actual.observaciones = (asignacion_actual.observaciones or "") + f"\n[Traslado a {usuario_destino.nombre_completo}]: {observaciones}"
            asignacion_actual.save()
            
            # 2. Crear nueva asignación
            nueva_asignacion = Asignacion.objects.create(
                activo=activo,
                usuario=usuario_destino,
                fecha_asignacion=timezone.now().date(),
                observaciones=f"Trasladado desde {asignacion_actual.usuario.nombre_completo}. {observaciones}"
            )
            
            # 3. Registrar movimiento
            Movimiento.objects.create(
                activo=activo,
                tipo="traslado",
                fecha=timezone.now().date(),
                descripcion=f"Trasladado de {asignacion_actual.usuario.nombre_completo} a {usuario_destino.nombre_completo}. {observaciones}",
                realizado_por=request.user.username if request.user.is_authenticated else "Sistema",
                usuario_destino=usuario_destino
            )
            
            ActaAsignacion.objects.create(asignacion=nueva_asignacion)
            
            messages.success(request, f"Activo trasladado a {usuario_destino.nombre_completo}.")
            return redirect("inventario:detalle", pk=activo.pk)
    else:
        form = TrasladoForm()
        
    return render(request, "inventario/asignacion_form.html", {
        "form": form, "titulo": "Trasladar Activo", "activo": activo, "accion": "Trasladar"
    })

# ── Actas PDF ──────────────────────────────────────────────────────────────────

@login_required
def generar_acta_pdf(request, asignacion_pk):
    asignacion = get_object_or_404(Asignacion, pk=asignacion_pk)

    html_string = render_to_string("inventario/acta_pdf.html", {"asignacion": asignacion})
    pdf_bytes = weasyprint.HTML(
        string=html_string, base_url=request.build_absolute_uri("/")
    ).write_pdf()

    # ── Persist PDF in ActaAsignacion if not already saved ─────────────────
    acta = getattr(asignacion, "acta", None)
    if acta and not acta.pdf_generado:
        filename = f"acta_{asignacion.activo.serial}_{asignacion.usuario.documento_identidad}.pdf"
        acta.pdf_generado.save(filename, ContentFile(pdf_bytes), save=True)

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = (
        f'inline; filename="acta_{asignacion.activo.serial}'
        f'_{asignacion.usuario.documento_identidad}.pdf"'
    )
    return response

@login_required
def subir_acta_firmada(request, asignacion_pk):
    asignacion = get_object_or_404(Asignacion, pk=asignacion_pk)
    acta = getattr(asignacion, "acta", None)
    
    if not acta:
        messages.error(request, "No existe registro de acta para esta asignación.")
        return redirect("inventario:detalle", pk=asignacion.activo.pk)
        
    if request.method == "POST":
        form = SubirActaForm(request.POST, request.FILES)
        if form.is_valid():
            acta.escaneado_firmado = form.cleaned_data["escaneado_firmado"]
            acta.save()
            messages.success(request, "Acta firmada subida correctamente.")
            return redirect("inventario:detalle", pk=asignacion.activo.pk)
    else:
        form = SubirActaForm()
        
    return render(request, "inventario/asignacion_form.html", {
        "form": form,
        "titulo": "Subir Acta Firmada",
        "activo": asignacion.activo,
        "accion": "Subir",
    })


# ══════════════════════════════════════════════════════════════════════════════
# CRUD — CatalogoModelo
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def catalogo_json(request):
    """Devuelve modelos de catálogo filtrados por tipo_dispositivo (JSON)."""
    tipo = request.GET.get("tipo", "").strip()
    qs = CatalogoModelo.objects.all()
    if tipo:
        qs = qs.filter(tipo_dispositivo=tipo)
    data = [
        {
            "id": item.pk,
            "text": str(item),
            "marca": item.marca,
            "modelo": item.modelo,
        }
        for item in qs
    ]
    return JsonResponse({"catalogo": data})


@login_required
def lista_catalogo(request):
    from .models import TIPOS
    qs = CatalogoModelo.objects.all()

    tipo = request.GET.get("tipo", "")
    q = request.GET.get("q", "").strip()

    if tipo:
        qs = qs.filter(tipo_dispositivo=tipo)
    if q:
        qs = qs.filter(
            Q(marca__icontains=q) | Q(modelo__icontains=q)
        )

    ctx = {"catalogo": qs, "tipos": TIPOS, "filtro_tipo": tipo, "filtro_q": q}
    return render(request, "inventario/catalogo_lista.html", ctx)


@login_required
def crear_catalogo(request):
    if request.method == "POST":
        form = CatalogoModeloForm(request.POST)
        if form.is_valid():
            obj = form.save()
            messages.success(request, f"Modelo de catálogo «{obj}» creado.")
            return redirect("inventario:catalogo_lista")
        else:
            messages.error(request, "Corrige los errores del formulario.")
    else:
        form = CatalogoModeloForm()

    return render(request, "inventario/form.html", {"form": form, "titulo": "Nuevo Modelo de Catálogo"})


@login_required
def editar_catalogo(request, pk):
    obj = get_object_or_404(CatalogoModelo, pk=pk)
    if request.method == "POST":
        form = CatalogoModeloForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, f"Modelo de catálogo «{obj}» actualizado.")
            return redirect("inventario:catalogo_lista")
        else:
            messages.error(request, "Corrige los errores del formulario.")
    else:
        form = CatalogoModeloForm(instance=obj)

    return render(request, "inventario/form.html", {"form": form, "titulo": "Editar Modelo de Catálogo"})


# ══════════════════════════════════════════════════════════════════════════════
# Exportar inventario a Excel — selección de columnas
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def exportar_opciones(request):
    secciones = [
        {
            "nombre": "Información general",
            "campos": [
                {"key": "id", "label": "ID"},
                {"key": "tipo", "label": "Tipo de dispositivo"},
                {"key": "marca", "label": "Marca"},
                {"key": "modelo", "label": "Modelo"},
                {"key": "serial", "label": "Serial"},
                {"key": "estado", "label": "Estado"},
                {"key": "ubicacion", "label": "Ubicación física"},
                {"key": "fecha_compra", "label": "Fecha de compra"},
                {"key": "proveedor", "label": "Proveedor"},
                {"key": "valor_compra", "label": "Valor de compra"},
                {"key": "observaciones", "label": "Observaciones"},
            ],
        },
        {
            "nombre": "Garantía",
            "campos": [
                {"key": "garantia_meses", "label": "Garantía fábrica (meses)"},
                {"key": "garantia_extendida", "label": "Garantía extendida"},
                {"key": "garantia_anos", "label": "Años garantía extendida"},
                {"key": "en_garantia", "label": "En garantía"},
                {"key": "fecha_vencimiento_garantia", "label": "Fecha vencimiento garantía"},
            ],
        },
        {
            "nombre": "Escritorio / Portátil",
            "campos": [
                {"key": "nombre_equipo", "label": "Nombre del equipo"},
                {"key": "disco_capacidad", "label": "Capacidad disco"},
                {"key": "tipo_disco", "label": "Tipo de disco"},
                {"key": "ram", "label": "RAM"},
                {"key": "procesador", "label": "Procesador"},
                {"key": "sistema_operativo", "label": "Sistema operativo"},
                {"key": "licencia_so", "label": "Licencia SO"},
                {"key": "usuario_red", "label": "Usuario de red"},
                {"key": "usuario_admin_local", "label": "Admin local"},
                {"key": "ip_equipo", "label": "IP del equipo"},
                {"key": "mac_equipo", "label": "MAC del equipo"},
            ],
        },
        {
            "nombre": "Celular",
            "campos": [
                {"key": "imei", "label": "IMEI"},
                {"key": "almacenamiento", "label": "Almacenamiento"},
                {"key": "ram_celular", "label": "RAM"},
                {"key": "procesador_celular", "label": "Procesador"},
                {"key": "tipo_disco_celular", "label": "Tipo de disco"},
                {"key": "cuenta_correo_dispositivo", "label": "Cuenta correo"},
                {"key": "numero_linea", "label": "Número de línea"},
                {"key": "operador", "label": "Operador"},
            ],
        },
        {
            "nombre": "Teléfono fijo",
            "campos": [
                {"key": "extension", "label": "Extensión"},
                {"key": "puerto_jack", "label": "Puerto / Jack"},
                {"key": "linea_asignada", "label": "Línea asignada"},
            ],
        },
        {
            "nombre": "Monitor",
            "campos": [
                {"key": "pulgadas", "label": "Pulgadas"},
                {"key": "resolucion", "label": "Resolución"},
                {"key": "tipo_panel", "label": "Tipo de panel"},
                {"key": "conectores", "label": "Conectores"},
            ],
        },
        {
            "nombre": "Asignación",
            "campos": [
                {"key": "asignado_a", "label": "Asignado a"},
                {"key": "documento_usuario", "label": "Documento usuario"},
                {"key": "area_usuario", "label": "Área usuario"},
                {"key": "fecha_asignacion", "label": "Fecha asignación"},
            ],
        },
        {
            "nombre": "Metadatos",
            "campos": [
                {"key": "fecha_creacion", "label": "Fecha creación"},
                {"key": "ultima_actualizacion", "label": "Última actualización"},
            ],
        },
    ]
    return render(request, "inventario/inventario_exportar_opciones.html", {"secciones": secciones})
