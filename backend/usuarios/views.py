from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from .models import Usuario
from .forms import UsuarioForm

# ── Importación masiva desde Excel ───────────────────────────────────────────
# Nombres de columna aceptados del archivo (case-insensitive). Cada entrada:
# columna_excel -> (campo_modelo, transformador(valor_crudo))
import openpyxl

CAMPOS_IMPORTACION = {
    "nombre completo": ("nombre_completo", "_reordenar_nombre"),
    "identificación": ("documento_identidad", None),
    "identificacion": ("documento_identidad", None),
    "documento": ("documento_identidad", None),
    "cargo": ("cargo", None),
    "área": ("area", None),
    "area": ("area", None),
    "número celular": ("telefono", None),
    "numero celular": ("telefono", None),
    "celular": ("telefono", None),
    "teléfono": ("telefono", None),
    "telefono": ("telefono", None),
    "correo corporativo": ("correo", None),
    "correo": ("correo", None),
    "correo electrónico": ("correo", None),
    "correo electronico": ("correo", None),
    "email": ("correo", None),
}


def _reordenar_nombre(valor):
    """'CALLE RIVERA BAIRON NICOLAS' -> 'Bairon Nicolas Calle Rivera'.

    Regla simple: primeras 2 palabras = apellidos, el resto = nombres.
    """
    partes = str(valor).strip().title().split()
    if len(partes) <= 2:
        return " ".join(partes)
    apellidos = partes[:2]
    nombres = partes[2:]
    return " ".join(nombres + apellidos)


def _parsear_excel_usuarios(archivo):
    """Lee la primera hoja de un .xlsx y retorna (filas, advertencias)."""
    wb = openpyxl.load_workbook(archivo, read_only=True, data_only=True)
    ws = wb.worksheets[0]

    # Mapa de índices de columna -> campo_modelo según la fila de headers
    header_map = {}
    headers = [str(c.value).strip() if c.value is not None else "" for c in next(ws.iter_rows(min_row=1, max_row=1))]
    for idx, header in enumerate(headers):
        campo = CAMPOS_IMPORTACION.get(header.lower())
        if campo:
            header_map[idx] = campo

    advertencias = []
    if not any(campo[0] == "documento_identidad" for campo in header_map.values()):
        advertencias.append('No se encontró la columna "Identificación" — nadie se puede importar sin documento.')

    filas = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        registro = {
            "nombre_completo": "", "documento_identidad": "", "cargo": "",
            "area": "", "telefono": "", "correo": "",
        }
        for idx, campo in header_map.items():
            valor = row[idx] if idx < len(row) else None
            if valor is None:
                continue
            nombre_campo, transformador = campo[:2]
            if transformador == "_reordenar_nombre":
                registro[nombre_campo] = _reordenar_nombre(valor)
            else:
                registro[nombre_campo] = str(valor).strip()

        # Ignorar filas totalmente vacías
        if not any(registro.values()):
            continue

        documento = registro["documento_identidad"]
        nombre = registro["nombre_completo"]
        if not documento:
            estado = "error_falta_documento"
        elif Usuario.objects.filter(documento_identidad=documento).exists():
            estado = "duplicado"
        elif not nombre:
            estado = "error_falta_nombre"
        else:
            estado = "ok"

        filas.append({"datos": registro, "estado": estado})
    wb.close()
    return filas, advertencias


@login_required
def importar_usuarios(request):
    if request.method == "POST":
        archivo = request.FILES.get("archivo")
        if not archivo:
            messages.error(request, "Debes seleccionar un archivo .xlsx")
            return redirect("usuarios:importar")
        if not archivo.name.lower().endswith(".xlsx"):
            messages.error(request, "El archivo debe ser .xlsx (Excel)")
            return redirect("usuarios:importar")

        try:
            filas, advertencias = _parsear_excel_usuarios(archivo)
        except Exception:
            messages.error(request, "No se pudo leer el archivo. ¿Es un .xlsx válido?")
            return redirect("usuarios:importar")

        request.session["importar_usuarios_filas"] = filas
        request.session["importar_usuarios_nombre"] = archivo.name
        if advertencias:
            for advertencia in advertencias:
                messages.warning(request, advertencia)

        resumen = {
            "ok": sum(1 for f in filas if f["estado"] == "ok"),
            "duplicados": sum(1 for f in filas if f["estado"] == "duplicado"),
            "errores": sum(1 for f in filas if f["estado"].startswith("error")),
            "total": len(filas),
        }
        return render(request, "usuarios/importar_preview.html", {
            "filas": filas,
            "resumen": resumen,
            "nombre_archivo": archivo.name,
        })

    return render(request, "usuarios/importar.html")


@login_required
def confirmar_importar_usuarios(request):
    if request.method != "POST":
        return redirect("usuarios:importar")

    filas = request.session.pop("importar_usuarios_filas", None)
    request.session.pop("importar_usuarios_nombre", None)
    if filas is None:
        messages.error(request, "La vista previa expiró. Vuelve a subir el archivo.")
        return redirect("usuarios:importar")

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
        datos = fila["datos"]
        # Doble verificación contra duplicados (por si alguien lo creó entre medio)
        if Usuario.objects.filter(documento_identidad=datos["documento_identidad"]).exists():
            duplicados += 1
            continue
        try:
            Usuario.objects.create(**datos)
            creados += 1
        except Exception:
            errores += 1

    messages.success(
        request,
        f"Importación terminada: {creados} usuarios creados, "
        f"{duplicados} omitidos por duplicado, {errores} con error."
    )
    return redirect("usuarios:lista")


@login_required
def lista_usuarios(request):
    q = request.GET.get("q", "").strip()
    area = request.GET.get("area", "").strip()
    estado = request.GET.get("estado", "").strip()

    qs = Usuario.objects.all()

    if q:
        qs = qs.filter(
            Q(nombre_completo__icontains=q) | Q(documento_identidad__icontains=q)
        )
    if area:
        qs = qs.filter(area__icontains=area)
    if estado:
        qs = qs.filter(estado=estado)

    areas = Usuario.objects.values_list("area", flat=True).distinct().order_by("area")

    context = {
        "usuarios": qs,
        "areas": areas,
        "q": q,
        "area_sel": area,
        "estado_sel": estado,
        "total": qs.count(),
        "activos": qs.filter(estado="activo").count(),
        "inactivos": qs.filter(estado="inactivo").count(),
    }

    # HTMX: retorna solo la tabla parcial
    if request.headers.get("HX-Request"):
        return render(request, "usuarios/partials/tabla.html", context)

    return render(request, "usuarios/lista.html", context)


@login_required
def detalle_usuario(request, pk):
    usuario = get_object_or_404(Usuario, pk=pk)
    from inventario.models import Asignacion
    asignaciones = Asignacion.objects.filter(usuario=usuario, activa=True).select_related("activo")
    activos = []
    for asignacion in asignaciones:
        activo = asignacion.activo
        activo.fecha_asignacion = asignacion.fecha_asignacion
        activos.append(activo)
    context = {
        "usuario": usuario,
        "activos": activos,
    }
    return render(request, "usuarios/detalle.html", context)


@login_required
def crear_usuario(request):
    if request.method == "POST":
        form = UsuarioForm(request.POST, request.FILES)
        if form.is_valid():
            usuario = form.save()
            messages.success(request, f"Usuario «{usuario.nombre_completo}» creado correctamente.")
            return redirect("usuarios:detalle", pk=usuario.pk)
    else:
        form = UsuarioForm()

    return render(request, "usuarios/form.html", {"form": form, "titulo": "Nuevo usuario"})


@login_required
def editar_usuario(request, pk):
    usuario = get_object_or_404(Usuario, pk=pk)
    if request.method == "POST":
        form = UsuarioForm(request.POST, request.FILES, instance=usuario)
        if form.is_valid():
            form.save()
            messages.success(request, f"Usuario «{usuario.nombre_completo}» actualizado.")
            return redirect("usuarios:detalle", pk=usuario.pk)
    else:
        form = UsuarioForm(instance=usuario)

    return render(request, "usuarios/form.html", {
        "form": form,
        "titulo": f"Editar — {usuario.nombre_completo}",
        "usuario": usuario,
    })


@login_required
def toggle_estado_usuario(request, pk):
    """Activa o desactiva un usuario. Nunca se elimina."""
    usuario = get_object_or_404(Usuario, pk=pk)
    if request.method == "POST":
        if usuario.is_activo:
            usuario.desactivar()
            messages.warning(request, f"Usuario «{usuario.nombre_completo}» desactivado.")
        else:
            usuario.activar()
            messages.success(request, f"Usuario «{usuario.nombre_completo}» activado.")
    return redirect("usuarios:detalle", pk=usuario.pk)
