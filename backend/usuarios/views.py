from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponse
import openpyxl

from .models import Usuario
from .forms import UsuarioForm
from accounts.permisos import requiere_permiso

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


@requiere_permiso("usuarios", "escritura")
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


@requiere_permiso("usuarios", "escritura")
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


@requiere_permiso("usuarios", "lectura")
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


@requiere_permiso("usuarios", "lectura")
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


@requiere_permiso("usuarios", "escritura")
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


@requiere_permiso("usuarios", "escritura")
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


@requiere_permiso("usuarios", "escritura")
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


@requiere_permiso("usuarios", "lectura")
def descargar_plantilla_usuarios(request):
    """Descarga plantilla Excel con headers y fila de ejemplo para importación de usuarios."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Plantilla Usuarios"

    headers = [
        "Nombre Completo",
        "Identificación",
        "Cargo",
        "Área",
        "Número Celular",
        "Correo Corporativo",
    ]

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
        "Calle Rivera Bairon Nicolas",  # Nombre Completo (apellidos primero, luego nombres)
        "100200300",                    # Identificación (documento único)
        "Analista de Sistemas",         # Cargo
        "Tecnología",                   # Área
        "3001234567",                   # Número Celular
        "bcalle@redihos.com",           # Correo Corporativo
    ]

    for col_idx, valor in enumerate(ejemplo, 1):
        cell = ws.cell(row=2, column=col_idx, value=valor)
        cell.border = thin_border
        cell.alignment = openpyxl.styles.Alignment(wrap_text=True, vertical="top")

    # Segunda fila de ejemplo
    ejemplo2 = [
        "Lopez Gomez Marta",
        "200300400",
        "Contadora",
        "Finanzas",
        "3104567890",
        "mlopez@redihos.com",
    ]

    for col_idx, valor in enumerate(ejemplo2, 1):
        cell = ws.cell(row=3, column=col_idx, value=valor)
        cell.border = thin_border
        cell.alignment = openpyxl.styles.Alignment(wrap_text=True, vertical="top")

    for col_idx in range(1, 7):
        col_letter = openpyxl.utils.get_column_letter(col_idx)
        ws.column_dimensions[col_letter].width = 28

    # Hoja de instrucciones
    ws_inst = wb.create_sheet("Instrucciones")
    instrucciones = [
        ["INSTRUCCIONES DE USO"],
        [""],
        ["1. Complete la hoja 'Plantilla Usuarios' copiando y pegando sus datos."],
        ["2. No elimine ni reordene las columnas; solo agregue filas debajo de los ejemplos."],
        ["3. El archivo debe guardarse como .xlsx (Excel 2007+)"],
        [""],
        ["CAMPOS OBLIGATORIOS:"],
        ["  - Identificación: único, máximo 50 caracteres (clave para evitar duplicados)"],
        ["  - Nombre Completo: formato 'Apellidos Nombres' (ej. 'Calle Rivera Bairon Nicolas')"],
        ["     El sistema reordena automáticamente: primeras 2 palabras = apellidos,"],
        ["     resto = nombres → 'Bairon Nicolas Calle Rivera'"],
        [""],
        ["CAMPOS OPCIONALES:"],
        ["  - Cargo, Área: texto libre"],
        ["  - Número Celular: solo dígitos, sin espacios ni guiones (ej. 3001234567)"],
        ["  - Correo Corporativo: formato email válido"],
        [""],
        ["IMPORTANTE:"],
        ["  - La Identificación es única. Si ya existe en el sistema, la fila se omitirá."],
        ["  - Las filas sin Identificación o sin Nombre se marcarán como error."],
        ["  - No modifique los encabezados; el sistema los lee por nombre exacto."],
        ["  - Columnas extra se ignoran; no modifique el orden de las columnas."],
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
    response["Content-Disposition"] = 'attachment; filename="plantilla_importar_usuarios.xlsx"'
    wb.save(response)
    return response
