from datetime import date, datetime
from decimal import Decimal
import base64
import io
import os

import qrcode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
import openpyxl

from administracion.models import ConfiguracionSistema

from .forms import (
    ActivoForm, CatalogoModeloForm, AsignacionForm,
    DevolucionForm, TrasladoForm, SubirActaForm,
)
from .models import Activo, Asignacion, CatalogoModelo, Movimiento, ActaAsignacion, TIPOS, ESTADOS
from accounts.permisos import requiere_permiso


# ── Lista ──────────────────────────────────────────────────────────────────────

@requiere_permiso("inventario", "lectura")
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

@requiere_permiso("inventario", "lectura")
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

@requiere_permiso("inventario", "escritura")
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

@requiere_permiso("inventario", "escritura")
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

@requiere_permiso("inventario", "escritura")
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

@requiere_permiso("inventario", "escritura")
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

@requiere_permiso("inventario", "escritura")
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

@requiere_permiso("inventario", "escritura")
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

@requiere_permiso("inventario", "lectura")
def generar_acta_pdf(request, asignacion_pk):
    import weasyprint

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


# ── Etiquetas QR ───────────────────────────────────────────────────────────────

LOGO_PATH = os.path.join(settings.BASE_DIR, "static", "img", "logo_redihos_mark.png")


def _qr_png_bytes(url):
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=7,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def _qr_data_uri(url):
    return "data:image/png;base64," + base64.b64encode(_qr_png_bytes(url)).decode("ascii")


def _etiqueta_context(request, activo):
    config = ConfiguracionSistema.get_config()
    return {
        "serial": activo.serial,
        "tipo": activo.get_tipo_dispositivo_display(),
        "marca": activo.marca,
        "modelo": activo.modelo,
        "numero_interno": activo.numero_interno,
        "qr": _qr_data_uri(
            request.build_absolute_uri(reverse("inventario:detalle", args=[activo.pk]))
        ),
        "logo_path": LOGO_PATH,
        "config": config,
    }


def _render_etiquetas_pdf(request, activos, filename):
    import weasyprint

    labels = [_etiqueta_context(request, a) for a in activos]
    html_string = render_to_string("inventario/etiqueta_pdf.html", {"labels": labels})
    pdf_bytes = weasyprint.HTML(
        string=html_string, base_url=request.build_absolute_uri("/")
    ).write_pdf()

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response


@requiere_permiso("inventario", "lectura")
def qr_etiqueta_pdf(request, pk):
    activo = get_object_or_404(Activo, pk=pk)
    return _render_etiquetas_pdf(request, [activo], f"etiqueta_{activo.serial}.pdf")


@requiere_permiso("inventario", "lectura")
def qr_etiquetas_masivas(request):
    if request.method == "POST":
        ids = [pk for pk in request.POST.getlist("activos") if pk]
        activos = Activo.objects.filter(pk__in=ids).order_by("serial")
        if not activos:
            messages.error(request, "Selecciona al menos un activo para generar etiquetas.")
            return redirect("inventario:etiquetas")
        return _render_etiquetas_pdf(request, activos, "etiquetas_qr.pdf")

    activos = Activo.objects.all().order_by("serial")
    return render(request, "inventario/etiquetas_seleccion.html", {"activos": activos})


@requiere_permiso("inventario", "lectura")
def qr_imagen(request, pk):
    activo = get_object_or_404(Activo, pk=pk)
    png = _qr_png_bytes(
        request.build_absolute_uri(reverse("inventario:detalle", args=[activo.pk]))
    )
    response = HttpResponse(png, content_type="image/png")
    response["Cache-Control"] = "public, max-age=86400"
    return response

@requiere_permiso("inventario", "escritura")
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

@requiere_permiso("inventario", "lectura")
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


@requiere_permiso("inventario", "lectura")
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


@requiere_permiso("inventario", "escritura")
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


@requiere_permiso("inventario", "escritura")
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

@requiere_permiso("inventario", "lectura")
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


# ── Importación masiva de Activos desde Excel ───────────────────────────────────

# Mapeo inverso: label del Excel -> (campo_modelo, transformador)
# Basado en CAMPOS_INVENTARIO de reports.views (mismos labels)
LABEL_TO_CAMPO = {
    "ID": ("id", None),
    "Tipo de dispositivo": ("tipo_dispositivo", None),
    "Marca": ("marca", None),
    "Modelo": ("modelo", None),
    "Serial": ("serial", None),
    "Estado": ("estado", None),
    "Ubicación física": ("ubicacion_fisica", None),
    "Fecha de compra": ("fecha_compra", None),
    "Proveedor": ("proveedor", None),
    "Valor de compra": ("valor_compra", None),
    "Garantía fábrica (meses)": ("garantia_fabrica_meses", None),
    "Garantía extendida": ("garantia_extendida", None),
    "Años garantía extendida": ("anios_garantia_extendida", None),
    "En garantía": ("en_garantia", None),
    "Fecha vencimiento garantía": ("fecha_vencimiento_garantia", None),
    "Observaciones": ("observaciones", None),
    "Nombre del equipo": ("nombre_equipo", None),
    "Capacidad disco": ("disco_capacidad", None),
    "Tipo de disco": ("tipo_disco", None),
    "RAM": ("ram", None),
    "Procesador": ("procesador", None),
    "Sistema operativo": ("sistema_operativo", None),
    "Licencia SO": ("licencia_so", None),
    "Usuario de red": ("usuario_red", None),
    "Admin local": ("usuario_admin_local", None),
    "IP del equipo": ("ip_equipo", None),
    "MAC del equipo": ("mac_equipo", None),
    "IMEI": ("imei", None),
    "Almacenamiento": ("almacenamiento", None),
    "RAM (celular)": ("ram_celular", None),
    "Procesador (celular)": ("procesador_celular", None),
    "Tipo de disco (celular)": ("tipo_disco_celular", None),
    "Correo dispositivo": ("cuenta_correo_dispositivo", None),
    "Número de línea": ("numero_linea", None),
    "Operador": ("operador", None),
    "Extensión": ("extension", None),
    "Puerto / Jack": ("puerto_jack", None),
    "Línea asignada": ("linea_asignada", None),
    "Pulgadas": ("pulgadas", None),
    "Resolución": ("resolucion", None),
    "Tipo de panel": ("tipo_panel", None),
    "Conectores": ("conectores", None),
    "Asignado a": ("asignado_a", None),  # se ignora en import (FK)
    "Documento usuario": ("documento_usuario", None),  # se ignora
    "Área usuario": ("area_usuario", None),  # se ignora
    "Fecha asignación": ("fecha_asignacion", None),  # se ignora
    "Fecha creación": ("fecha_creacion", None),  # auto
    "Última actualización": ("fecha_actualizacion", None),  # auto
}

# Campos que se pueden importar directamente (no FK, no auto)
CAMPOS_IMPORTABLES = {
    k for k in LABEL_TO_CAMPO
    if LABEL_TO_CAMPO[k][0] not in ("asignado_a", "documento_usuario", "area_usuario", "fecha_asignacion", "fecha_creacion", "ultima_actualizacion")
}

# Valores válidos para choices (case-insensitive)
TIPOS_VALIDOS = {v.lower(): k for k, v in TIPOS}
ESTADOS_VALIDOS = {v.lower(): k for k, v in ESTADOS}


def _normalizar_valor(label, valor):
    """Normaliza un valor según el tipo de campo."""
    if valor is None or str(valor).strip() == "":
        return ""
    valor = str(valor).strip()
    campo = LABEL_TO_CAMPO.get(label, ("", None))[0]
    if campo == "tipo_dispositivo":
        return TIPOS_VALIDOS.get(valor.lower(), valor)
    if campo == "estado":
        return ESTADOS_VALIDOS.get(valor.lower(), valor)
    if campo in ("garantia_extendida", "en_garantia"):
        return valor.lower() in ("sí", "si", "yes", "true", "1")
    if campo == "valor_compra":
        try:
            # quita $, espacios, y separadores de miles (puntos/comas)
            limpio = valor.replace("$", "").replace(" ", "").replace(",", "").replace(".", "")
            return float(limpio)
        except Exception:
            return None
    if campo in ("garantia_fabrica_meses", "anios_garantia_extendida"):
        try:
            return int(valor)
        except Exception:
            return None
    if campo == "fecha_compra":
        # intenta varios formatos
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                dt = datetime.strptime(valor, fmt).date()
                return dt.isoformat()  # string ISO para guardar en sesión (JSON)
            except Exception:
                pass
        return None
    if campo == "pulgadas":
        try:
            return float(valor.replace(",", "."))
        except Exception:
            return None
    return valor


def _parsear_excel_activos(archivo):
    """Lee la primera hoja de un .xlsx y retorna (filas, advertencias)."""
    wb = openpyxl.load_workbook(archivo, read_only=True, data_only=True)
    ws = wb.worksheets[0]

    # Mapa de índices de columna -> campo_modelo según la fila de headers
    header_map = {}
    headers = [str(c.value).strip() if c.value is not None else "" for c in next(ws.iter_rows(min_row=1, max_row=1))]
    for idx, header in enumerate(headers):
        if header in CAMPOS_IMPORTABLES:
            header_map[idx] = header

    advertencias = []
    if "Serial" not in header_map.values():
        advertencias.append('No se encontró la columna "Serial" — es obligatoria para importar.')

    filas = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        registro = {}
        for idx, label in header_map.items():
            valor = row[idx] if idx < len(row) else None
            if valor is None or str(valor).strip() == "":
                continue
            campo = LABEL_TO_CAMPO.get(label, ("", None))[0]
            if not campo:
                continue
            valor_norm = _normalizar_valor(label, valor)
            if valor_norm not in ("", None):
                registro[campo] = valor_norm

        # Ignorar filas totalmente vacías
        if not registro:
            continue

        serial = registro.get("serial", "")
        tipo = registro.get("tipo_dispositivo", "")
        if not serial:
            estado = "error_falta_serial"
        elif Activo.objects.filter(serial=serial).exists():
            estado = "duplicado"
        elif not tipo:
            estado = "error_falta_tipo"
        else:
            estado = "ok"

        # Para la vista previa mostramos los campos principales
        filas.append({
            "datos": registro,
            "estado": estado,
            "preview": {
                "tipo": tipo,
                "marca": registro.get("marca", ""),
                "modelo": registro.get("modelo", ""),
                "serial": serial,
            }
        })
    wb.close()
    return filas, advertencias


@requiere_permiso("inventario", "escritura")
def importar_activos(request):
    if request.method == "POST":
        archivo = request.FILES.get("archivo")
        if not archivo:
            messages.error(request, "Debes seleccionar un archivo .xlsx")
            return redirect("inventario:importar")
        if not archivo.name.lower().endswith(".xlsx"):
            messages.error(request, "El archivo debe ser .xlsx (Excel)")
            return redirect("inventario:importar")

        try:
            filas, advertencias = _parsear_excel_activos(archivo)
        except Exception:
            messages.error(request, "No se pudo leer el archivo. ¿Es un .xlsx válido?")
            return redirect("inventario:importar")

        request.session["importar_activos_filas"] = filas
        request.session["importar_activos_nombre"] = archivo.name
        if advertencias:
            for advertencia in advertencias:
                messages.warning(request, advertencia)

        resumen = {
            "ok": sum(1 for f in filas if f["estado"] == "ok"),
            "duplicados": sum(1 for f in filas if f["estado"] == "duplicado"),
            "errores": sum(1 for f in filas if f["estado"].startswith("error")),
            "total": len(filas),
        }
        return render(request, "inventario/importar_preview.html", {
            "filas": filas,
            "resumen": resumen,
            "nombre_archivo": archivo.name,
        })

    return render(request, "inventario/importar.html")


@requiere_permiso("inventario", "escritura")
def confirmar_importar_activos(request):
    if request.method != "POST":
        return redirect("inventario:importar")

    filas = request.session.pop("importar_activos_filas", None)
    request.session.pop("importar_activos_nombre", None)
    if filas is None:
        messages.error(request, "La vista previa expiró. Vuelve a subir el archivo.")
        return redirect("inventario:importar")

    creados = 0
    duplicados = 0
    errores = 0
    for fila in filas:
        if fila["estado"] != "ok":
            if fila["estado"] == "duplicado":
                duplicados += 1
            else:
                errores += 1
            continue
        datos = fila["datos"].copy()
        # Convertir fecha ISO string a date object
        fc = datos.get("fecha_compra")
        if isinstance(fc, str):
            try:
                datos["fecha_compra"] = date.fromisoformat(fc)
            except Exception:
                datos.pop("fecha_compra", None)
        # Doble verificación contra duplicados
        if Activo.objects.filter(serial=datos.get("serial")).exists():
            duplicados += 1
            continue
        try:
            Activo.objects.create(**datos)
            creados += 1
        except Exception:
            errores += 1

    messages.success(
        request,
        f"Importación terminada: {creados} activos creados, "
        f"{duplicados} omitidos por duplicado, {errores} con error."
    )
    return redirect("inventario:lista")


@requiere_permiso("inventario", "lectura")
def descargar_plantilla_activos(request):
    """Descarga plantilla Excel con headers y fila de ejemplo."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Plantilla Activos"

    # Headers en el mismo orden que CAMPOS_IMPORTABLES (columnas principales primero)
    headers = [
        "Tipo de dispositivo",
        "Marca",
        "Modelo",
        "Serial",
        "Estado",
        "Ubicación física",
        "Fecha de compra",
        "Proveedor",
        "Valor de compra",
        "Garantía fábrica (meses)",
        "Garantía extendida",
        "Años garantía extendida",
        "Observaciones",
        "Nombre del equipo",
        "Capacidad disco",
        "Tipo de disco",
        "RAM",
        "Procesador",
        "Sistema operativo",
        "Licencia SO",
        "Usuario de red",
        "Admin local",
        "IP del equipo",
        "MAC del equipo",
        "IMEI",
        "Almacenamiento",
        "RAM (celular)",
        "Procesador (celular)",
        "Tipo de disco (celular)",
        "Correo dispositivo",
        "Número de línea",
        "Operador",
        "Extensión",
        "Puerto / Jack",
        "Línea asignada",
        "Pulgadas",
        "Resolución",
        "Tipo de panel",
        "Conectores",
    ]

    # Estilo header
    header_font = openpyxl.styles.Font(bold=True, color="FFFFFF")
    header_fill = openpyxl.styles.PatternFill(start_color="0156A6", end_color="0156A6", fill_type="solid")
    header_alignment = openpyxl.styles.Alignment(horizontal="center", vertical="center", wrap_text=True)
    thin_border = openpyxl.styles.Border(
        left=openpyxl.styles.Side(style="thin"),
        right=openpyxl.styles.Side(style="thin"),
        top=openpyxl.styles.Side(style="thin"),
        bottom=openpyxl.styles.Side(style="thin"),
    )

    for col_idx, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment
        cell.border = thin_border

    # Fila de ejemplo
    ejemplo = [
        "Portátil",                    # Tipo de dispositivo
        "Dell",                        # Marca
        "Latitude 3420",               # Modelo
        "SN123456",                    # Serial
        "Disponible",                  # Estado
        "Oficina 101",                 # Ubicación física
        "2024-03-15",                  # Fecha de compra (YYYY-MM-DD)
        "Dell Corp",                   # Proveedor
        "1200000",                     # Valor de compra
        "24",                          # Garantía fábrica (meses)
        "Sí",                          # Garantía extendida
        "2",                           # Años garantía extendida
        "Equipo nuevo para desarrollador",  # Observaciones
        "DESK-DEV-01",                 # Nombre del equipo
        "512GB SSD",                   # Capacidad disco
        "SSD",                         # Tipo de disco
        "16GB",                        # RAM
        "Intel Core i5-1335U",         # Procesador
        "Windows 11 Pro",              # Sistema operativo
        "OEM-12345",                   # Licencia SO
        "jperez",                      # Usuario de red
        "adminlocal",                  # Admin local
        "192.168.1.50",                # IP del equipo
        "00:1A:2B:3C:4D:5E",           # MAC del equipo
        "",                            # IMEI (solo celular)
        "",                            # Almacenamiento (solo celular)
        "",                            # RAM (celular)
        "",                            # Procesador (celular)
        "",                            # Tipo de disco (celular)
        "",                            # Correo dispositivo (solo celular)
        "",                            # Número de línea (solo celular)
        "",                            # Operador (solo celular)
        "",                            # Extensión (solo teléfono fijo)
        "",                            # Puerto / Jack (solo teléfono fijo)
        "",                            # Línea asignada (solo teléfono fijo)
        "",                            # Pulgadas (solo monitor)
        "",                            # Resolución (solo monitor)
        "",                            # Tipo de panel (solo monitor)
        "",                            # Conectores (solo monitor)
    ]

    for col_idx, valor in enumerate(ejemplo, 1):
        cell = ws.cell(row=2, column=col_idx, value=valor)
        cell.border = thin_border
        cell.alignment = openpyxl.styles.Alignment(wrap_text=True, vertical="top")

    # Segunda fila de ejemplo (celular)
    ejemplo2 = [
        "Celular",
        "Samsung",
        "Galaxy S23",
        "IMEI123456789012345",
        "Asignado",
        "Bodega Central",
        "2024-01-10",
        "Samsung Colombia",
        "800000",
        "12",
        "No",
        "",
        "Entrega a gerente",
        "", "", "", "", "", "", "", "", "", "",
        "123456789012345",
        "256GB",
        "8GB",
        "Snapdragon 8 Gen 2",
        "UFS 4.0",
        "gerente@empresa.com",
        "3001234567",
        "Claro",
        "", "", "", "", "", "", "", "",
    ]

    for col_idx, valor in enumerate(ejemplo2, 1):
        cell = ws.cell(row=3, column=col_idx, value=valor)
        cell.border = thin_border
        cell.alignment = openpyxl.styles.Alignment(wrap_text=True, vertical="top")

    # Ajustar anchos de columna
    for col_idx in range(1, len(headers) + 1):
        col_letter = openpyxl.utils.get_column_letter(col_idx)
        ws.column_dimensions[col_letter].width = 22

    # Hoja de instrucciones
    ws_inst = wb.create_sheet("Instrucciones")
    instrucciones = [
        ["INSTRUCCIONES DE USO"],
        [""],
        ["1. Complete la hoja 'Plantilla Activos' copiando y pegando sus datos."],
        ["2. No elimine ni reordene las columnas; solo agregue filas debajo de los ejemplos."],
        ["3. El archivo debe guardarse como .xlsx (Excel 2007+)"],
        [""],
        ["CAMPOS OBLIGATORIOS:"],
        ["  - Serial: único, máximo 150 caracteres (clave para evitar duplicados)"],
        ["  - Tipo de dispositivo: exactamente uno de:"],
        ["      Celular, Equipo Escritorio, Portátil, Teléfono Fijo, Monitor"],
        ["  - Estado: exactamente uno de:"],
        ["      Disponible, Asignado, En mantenimiento, En reparación, Dado de baja"],
        [""],
        ["CAMPOS POR TIPO DE DISPOSITIVO (los demás déjelos vacíos):"],
        ["  - Portátil / Equipo Escritorio: Nombre del equipo, Capacidad disco, Tipo de disco,"],
        ["      RAM, Procesador, Sistema operativo, Licencia SO, Usuario de red,"],
        ["      Admin local, IP del equipo, MAC del equipo"],
        ["  - Celular: IMEI, Almacenamiento, RAM (celular), Procesador (celular),"],
        ["      Tipo de disco (celular), Correo dispositivo, Número de línea, Operador"],
        ["  - Teléfono Fijo: Extensión, Puerto / Jack, Línea asignada"],
        ["  - Monitor: Pulgadas, Resolución, Tipo de panel, Conectores"],
        [""],
        ["FORMATOS:"],
        ["  - Fecha de compra: YYYY-MM-DD (ej. 2024-03-15)"],
        ["  - Valor de compra: número entero o con punto decimal (ej. 1200000 o 1200000.50)"],
        ["  - Garantía extendida: Sí / No"],
        ["  - Valor de compra y Garantía fábrica: solo números"],
        ["  - IMEI: 15 dígitos sin espacios ni guiones"],
        ["  - MAC: formato XX:XX:XX:XX:XX:XX"],
        ["  - IP: formato IPv4 (ej. 192.168.1.50)"],
        ["  - Pulgadas: número decimal con punto (ej. 23.8)"],
        [""],
        ["IMPORTANTE:"],
        ["  - El Serial es único. Si ya existe en el sistema, la fila se omitirá."],
        ["  - Las filas sin Serial o sin Tipo de dispositivo se marcarán como error."],
        ["  - Los campos no listados arriba se ignoran (puede borrar columnas extra)."],
        ["  - No modifique los encabezados; el sistema los lee por nombre exacto."],
    ]

    for row_idx, line in enumerate(instrucciones, 1):
        cell = ws_inst.cell(row=row_idx, column=1, value=line[0])
        if row_idx == 1:
            cell.font = openpyxl.styles.Font(bold=True, size=14, color="0156A6")
        cell.alignment = openpyxl.styles.Alignment(wrap_text=True)

    ws_inst.column_dimensions["A"].width = 100

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = 'attachment; filename="plantilla_importar_activos.xlsx"'
    wb.save(response)
    return response
