from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Prefetch, Q
from django.db.models.functions import TruncMonth
from django.http import HttpResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.utils import timezone
import weasyprint
from openpyxl import Workbook

from inventario.models import Activo, Asignacion, Movimiento, TIPOS, ESTADOS
from mantenimiento.models import OrdenMantenimiento
from usuarios.models import Usuario


def _parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _shift_months(base_date, delta_months):
    year = base_date.year + (base_date.month - 1 + delta_months) // 12
    month = (base_date.month - 1 + delta_months) % 12 + 1
    return date(year, month, 1)


def _months_between(start_date, end_date):
    if start_date is None:
        return 0
    months = (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month)
    if end_date.day < start_date.day:
        months -= 1
    return max(months, 0)


def _build_activos_resumen():
    estados_map = dict(ESTADOS)
    tipos_map = dict(TIPOS)

    estados_counts = {key: 0 for key, _ in ESTADOS}
    for row in Activo.objects.values("estado").annotate(total=Count("id")):
        estados_counts[row["estado"]] = row["total"]

    tipos_counts = {key: 0 for key, _ in TIPOS}
    for row in Activo.objects.values("tipo_dispositivo").annotate(total=Count("id")):
        tipos_counts[row["tipo_dispositivo"]] = row["total"]

    activos_por_estado = [
        {"key": key, "label": estados_map.get(key, key), "total": total}
        for key, total in estados_counts.items()
    ]
    activos_por_tipo = [
        {"key": key, "label": tipos_map.get(key, key), "total": total}
        for key, total in tipos_counts.items()
    ]

    return activos_por_estado, activos_por_tipo


def _build_movimientos_mensuales(rango_fin):
    rango_inicio = _shift_months(rango_fin.replace(day=1), -11)
    qs = (
        Movimiento.objects.filter(fecha__gte=rango_inicio, fecha__lte=rango_fin)
        .annotate(mes=TruncMonth("fecha"))
        .values("mes")
        .annotate(total=Count("id"))
        .order_by("mes")
    )
    totales = {}
    for row in qs:
        mes = row["mes"]
        if hasattr(mes, "date"):
            mes = mes.date()
        totales[mes] = row["total"]

    meses = []
    for offset in range(12):
        mes = _shift_months(rango_inicio, offset)
        meses.append({"mes": mes, "total": totales.get(mes, 0)})
    return meses


def _build_costos(rango_fin, vida_util_meses=36):
    total = Decimal("0")
    depreciacion = Decimal("0")
    valor_actual = Decimal("0")
    items = []

    activos = Activo.objects.exclude(valor_compra__isnull=True).order_by("-valor_compra")
    for activo in activos:
        valor = activo.valor_compra or Decimal("0")
        meses = _months_between(activo.fecha_compra, rango_fin)
        meses = min(meses, vida_util_meses)
        if vida_util_meses > 0:
            dep = (valor * Decimal(meses) / Decimal(vida_util_meses)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        else:
            dep = Decimal("0.00")
        actual = (valor - dep).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        total += valor
        depreciacion += dep
        valor_actual += actual

        items.append({
            "activo": activo,
            "valor": valor,
            "depreciacion": dep,
            "valor_actual": actual,
            "meses": meses,
        })

    items.sort(key=lambda item: item["valor_actual"], reverse=True)
    return {
        "total": total,
        "depreciacion": depreciacion,
        "valor_actual": valor_actual,
        "items": items[:8],
        "vida_util": vida_util_meses,
    }


def _build_report_context(rango_inicio, rango_fin):
    activos_por_estado, activos_por_tipo = _build_activos_resumen()
    movimientos_mensuales = _build_movimientos_mensuales(rango_fin)
    costos = _build_costos(rango_fin)

    usuarios_activos = Usuario.objects.filter(estado="activo").count()
    usuarios_inactivos = Usuario.objects.filter(estado="inactivo").count()
    usuarios_por_area = (
        Usuario.objects.values("area")
        .annotate(total=Count("id"))
        .order_by("-total", "area")
    )

    movimientos_qs = (
        Movimiento.objects.filter(fecha__range=(rango_inicio, rango_fin))
        .select_related("activo", "usuario_destino")
        .order_by("-fecha", "-fecha_creacion")
    )

    return {
        "rango_inicio": rango_inicio,
        "rango_fin": rango_fin,
        "usuarios_activos": usuarios_activos,
        "usuarios_inactivos": usuarios_inactivos,
        "usuarios_por_area": usuarios_por_area,
        "activos_total": Activo.objects.count(),
        "activos_por_estado": activos_por_estado,
        "activos_por_tipo": activos_por_tipo,
        "movimientos_total": movimientos_qs.count(),
        "movimientos": movimientos_qs[:50],
        "movimientos_mensuales": movimientos_mensuales,
        "costos_total": costos["total"],
        "costos_depreciacion": costos["depreciacion"],
        "costos_valor_actual": costos["valor_actual"],
        "costos_items": costos["items"],
        "costos_vida_util": costos["vida_util"],
    }


@login_required
def index(request):
    today = timezone.now().date()
    rango_fin = _parse_date(request.GET.get("fin")) or today
    rango_inicio = _parse_date(request.GET.get("inicio")) or (rango_fin - timedelta(days=30))
    if rango_inicio > rango_fin:
        rango_inicio, rango_fin = rango_fin, rango_inicio

    context = _build_report_context(rango_inicio, rango_fin)
    return render(request, "reports/index.html", context)


@login_required
def inventario_pdf(request):
    today = timezone.now().date()
    context = _build_report_context(today - timedelta(days=30), today)
    activos = Activo.objects.prefetch_related(
        Prefetch(
            "asignaciones",
            queryset=Asignacion.objects.filter(activa=True).select_related("usuario"),
            to_attr="asignaciones_activas",
        )
    ).order_by("estado", "marca", "modelo")

    estados_counts = {key: 0 for key, _ in ESTADOS}
    for row in Activo.objects.values("estado").annotate(total=Count("id")):
        estados_counts[row["estado"]] = row["total"]

    context.update({
        "fecha_generacion": timezone.now(),
        "activos": activos,
        "disponibles": estados_counts.get("disponible", 0),
        "asignados": estados_counts.get("asignado", 0),
        "baja": estados_counts.get("dado_de_baja", 0),
    })

    html_string = render_to_string("reports/inventario_pdf.html", context)
    pdf_bytes = weasyprint.HTML(
        string=html_string, base_url=request.build_absolute_uri("/")
    ).write_pdf()

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="reporte_inventario.pdf"'
    return response


@login_required
def usuarios_pdf(request):
    usuarios = (
        Usuario.objects.annotate(
            activos_asignados=Count("asignaciones", filter=Q(asignaciones__activa=True))
        )
        .order_by("nombre_completo")
    )
    context = {
        "fecha_generacion": timezone.now(),
        "usuarios": usuarios,
    }

    html_string = render_to_string("reports/usuarios_pdf.html", context)
    pdf_bytes = weasyprint.HTML(
        string=html_string, base_url=request.build_absolute_uri("/")
    ).write_pdf()

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="reporte_usuarios.pdf"'
    return response


@login_required
def inventario_excel(request):
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws_resumen = wb.active
    ws_resumen.title = "Resumen"

    activos_por_estado, activos_por_tipo = _build_activos_resumen()

    ws_resumen.append(["Reporte Inventario", timezone.now().strftime("%Y-%m-%d %H:%M")])
    ws_resumen.append([])
    ws_resumen.append(["Total activos", Activo.objects.count()])
    ws_resumen.append([])
    ws_resumen.append(["Por estado", "Total"])
    for item in activos_por_estado:
        ws_resumen.append([item["label"], item["total"]])
    ws_resumen.append([])
    ws_resumen.append(["Por tipo", "Total"])
    for item in activos_por_tipo:
        ws_resumen.append([item["label"], item["total"]])

    ws_resumen["A1"].font = Font(bold=True, size=14, color="0156A6")
    ws_resumen.column_dimensions["A"].width = 24
    ws_resumen.column_dimensions["B"].width = 20

    ws_activos = wb.create_sheet(title="Activos")

    headers = [
        "ID", "Tipo", "Marca", "Modelo", "Serial", "Nombre equipo",
        "Estado", "Ubicacion fisica", "Fecha compra", "Proveedor",
        "Valor compra", "Garantia fabrica (meses)", "Garantia extendida",
        "Anios garantia extendida", "En garantia", "Fecha vencimiento garantia",
        "IMEI", "Almacenamiento", "RAM (celular)", "Procesador (celular)",
        "Tipo disco (celular)", "Correo dispositivo", "Numero linea", "Operador",
        "Disco capacidad", "Tipo disco", "RAM", "Procesador",
        "Sistema operativo", "Licencia SO", "Usuario red", "Usuario admin local",
        "IP equipo", "MAC equipo",
        "Extension", "Puerto jack", "Linea asignada",
        "Pulgadas", "Resolucion", "Tipo panel", "Conectores",
        "Asignado a", "Documento usuario", "Area usuario", "Fecha asignacion",
        "Observaciones", "Fecha creacion", "Ultima actualizacion",
    ]
    ws_activos.append(headers)

    header_fill = PatternFill(start_color="0156A6", end_color="0156A6", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    thin = Side(style="thin", color="D9D9D9")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    for col_idx in range(1, len(headers) + 1):
        cell = ws_activos.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = border

    ws_activos.freeze_panes = "A2"
    ws_activos.auto_filter.ref = f"A1:{get_column_letter(len(headers))}1"
    ws_activos.row_dimensions[1].height = 32

    activos = Activo.objects.prefetch_related(
        Prefetch(
            "asignaciones",
            queryset=Asignacion.objects.filter(activa=True).select_related("usuario"),
            to_attr="asignaciones_activas",
        )
    ).order_by("tipo_dispositivo", "marca", "modelo")

    valor_col = headers.index("Valor compra") + 1

    for row_idx, activo in enumerate(activos, start=2):
        asignacion = activo.asignaciones_activas[0] if activo.asignaciones_activas else None
        row = [
            activo.id,
            activo.get_tipo_dispositivo_display(),
            activo.marca,
            activo.modelo,
            activo.serial,
            getattr(activo, "nombre_equipo", "") or "",
            activo.get_estado_display(),
            activo.ubicacion_fisica,
            activo.fecha_compra.strftime("%Y-%m-%d") if activo.fecha_compra else "",
            activo.proveedor,
            float(activo.valor_compra) if activo.valor_compra else None,
            activo.garantia_fabrica_meses,
            "Si" if activo.garantia_extendida else "No",
            activo.anios_garantia_extendida,
            "Si" if activo.en_garantia else "No",
            activo.fecha_vencimiento_garantia.strftime("%Y-%m-%d") if activo.fecha_vencimiento_garantia else "",
            activo.imei or "",
            activo.almacenamiento,
            activo.ram_celular,
            activo.procesador_celular,
            activo.tipo_disco_celular,
            activo.cuenta_correo_dispositivo,
            activo.numero_linea,
            activo.operador,
            activo.disco_capacidad,
            activo.tipo_disco,
            activo.ram,
            activo.procesador,
            activo.sistema_operativo,
            activo.licencia_so,
            activo.usuario_red,
            activo.usuario_admin_local,
            activo.ip_equipo or "",
            activo.mac_equipo,
            activo.extension,
            activo.puerto_jack,
            activo.linea_asignada,
            float(activo.pulgadas) if activo.pulgadas else None,
            activo.resolucion,
            activo.tipo_panel,
            activo.conectores,
            asignacion.usuario.nombre_completo if asignacion else "",
            asignacion.usuario.documento_identidad if asignacion else "",
            asignacion.usuario.area if asignacion else "",
            asignacion.fecha_asignacion.strftime("%Y-%m-%d") if asignacion else "",
            activo.observaciones,
            activo.fecha_creacion.strftime("%Y-%m-%d %H:%M"),
            activo.fecha_actualizacion.strftime("%Y-%m-%d %H:%M"),
        ]
        ws_activos.append(row)
        for col_idx in range(1, len(headers) + 1):
            ws_activos.cell(row=row_idx, column=col_idx).border = border
        ws_activos.cell(row=row_idx, column=valor_col).number_format = '$#,##0'

    for col_idx, header in enumerate(headers, start=1):
        ws_activos.column_dimensions[get_column_letter(col_idx)].width = max(12, len(header) + 4)

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = "attachment; filename=reporte_inventario.xlsx"
    wb.save(response)
    return response


@login_required
def usuarios_excel(request):
    wb = Workbook()
    ws_resumen = wb.active
    ws_resumen.title = "Resumen"

    usuarios_activos = Usuario.objects.filter(estado="activo").count()
    usuarios_inactivos = Usuario.objects.filter(estado="inactivo").count()
    usuarios_por_area = (
        Usuario.objects.values("area")
        .annotate(total=Count("id"))
        .order_by("-total", "area")
    )
    usuarios_por_cargo = (
        Usuario.objects.values("cargo")
        .annotate(total=Count("id"))
        .order_by("-total", "cargo")
    )

    ws_resumen.append(["Reporte Usuarios", timezone.now().strftime("%Y-%m-%d %H:%M")])
    ws_resumen.append([])
    ws_resumen.append(["Usuarios activos", usuarios_activos])
    ws_resumen.append(["Usuarios inactivos", usuarios_inactivos])
    ws_resumen.append([])
    ws_resumen.append(["Por area", "Total"])
    for row in usuarios_por_area:
        ws_resumen.append([row["area"], row["total"]])
    ws_resumen.append([])
    ws_resumen.append(["Por cargo", "Total"])
    for row in usuarios_por_cargo:
        ws_resumen.append([row["cargo"], row["total"]])

    ws = wb.create_sheet(title="Usuarios")
    ws.append([
        "Nombre", "Documento", "Cargo", "Area", "Correo",
        "Telefono", "Estado", "Fecha creacion"
    ])

    for usuario in Usuario.objects.all().order_by("nombre_completo"):
        ws.append([
            usuario.nombre_completo,
            usuario.documento_identidad,
            usuario.cargo,
            usuario.area,
            usuario.correo,
            usuario.telefono,
            usuario.get_estado_display(),
            usuario.fecha_creacion.strftime("%Y-%m-%d"),
        ])

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = "attachment; filename=reporte_usuarios.xlsx"
    wb.save(response)
    return response


@login_required
def costos_excel(request):
    today = timezone.now().date()
    costos = _build_costos(today)

    wb = Workbook()
    ws_resumen = wb.active
    ws_resumen.title = "Resumen"
    ws_resumen.append(["Reporte Costos", timezone.now().strftime("%Y-%m-%d %H:%M")])
    ws_resumen.append([])
    ws_resumen.append(["Vida util (meses)", costos["vida_util"]])
    ws_resumen.append(["Valor compra total", float(costos["total"])])
    ws_resumen.append(["Depreciacion acumulada", float(costos["depreciacion"])])
    ws_resumen.append(["Valor actual estimado", float(costos["valor_actual"])])

    ws = wb.create_sheet(title="Costos")
    ws.append([
        "Activo", "Serial", "Tipo", "Valor compra",
        "Meses", "Depreciacion", "Valor actual"
    ])

    for item in costos["items"]:
        activo = item["activo"]
        ws.append([
            str(activo),
            activo.serial,
            activo.get_tipo_dispositivo_display(),
            float(item["valor"]),
            item["meses"],
            float(item["depreciacion"]),
            float(item["valor_actual"]),
        ])

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = "attachment; filename=reporte_costos.xlsx"
    wb.save(response)
    return response


@login_required
def movimientos_excel(request):
    today = timezone.now().date()
    rango_fin = _parse_date(request.GET.get("fin")) or today
    rango_inicio = _parse_date(request.GET.get("inicio")) or (rango_fin - timedelta(days=30))
    if rango_inicio > rango_fin:
        rango_inicio, rango_fin = rango_fin, rango_inicio

    movimientos = (
        Movimiento.objects.filter(fecha__range=(rango_inicio, rango_fin))
        .select_related("activo", "usuario_destino")
        .order_by("-fecha", "-fecha_creacion")
    )

    wb = Workbook()
    ws = wb.active
    ws.title = "Movimientos"
    ws.append([
        "Fecha", "Tipo", "Activo", "Serial", "Usuario destino",
        "Descripcion", "Realizado por"
    ])

    for mov in movimientos:
        ws.append([
            mov.fecha.strftime("%Y-%m-%d"),
            mov.get_tipo_display(),
            mov.activo.get_tipo_dispositivo_display(),
            mov.activo.serial,
            mov.usuario_destino.nombre_completo if mov.usuario_destino else "",
            mov.descripcion,
            mov.realizado_por,
        ])

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = "attachment; filename=reporte_movimientos.xlsx"
    wb.save(response)
    return response


@login_required
def mantenimiento_excel(request):
    today = timezone.now().date()
    rango_fin = _parse_date(request.GET.get("fin")) or today
    rango_inicio = _parse_date(request.GET.get("inicio")) or (rango_fin - timedelta(days=30))
    if rango_inicio > rango_fin:
        rango_inicio, rango_fin = rango_fin, rango_inicio

    ordenes = (
        OrdenMantenimiento.objects.filter(fecha_apertura__range=(rango_inicio, rango_fin))
        .select_related("activo", "plan")
        .order_by("-fecha_apertura", "-fecha_creacion")
    )

    wb = Workbook()
    ws = wb.active
    ws.title = "Ordenes"
    ws.append([
        "Fecha apertura",
        "Fecha cierre",
        "Tipo",
        "Estado",
        "Prioridad",
        "Activo",
        "Serial",
        "Plan",
        "Tecnico",
        "Costo estimado",
        "Costo real",
    ])

    for orden in ordenes:
        ws.append([
            orden.fecha_apertura.strftime("%Y-%m-%d") if orden.fecha_apertura else "",
            orden.fecha_cierre.strftime("%Y-%m-%d") if orden.fecha_cierre else "",
            orden.get_tipo_display(),
            orden.get_estado_display(),
            orden.get_prioridad_display(),
            f"{orden.activo.marca} {orden.activo.modelo}",
            orden.activo.serial,
            f"Plan #{orden.plan_id}" if orden.plan_id else "",
            orden.tecnico_asignado,
            float(orden.costo_estimado) if orden.costo_estimado else "",
            float(orden.costo_real) if orden.costo_real else "",
        ])

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = "attachment; filename=reporte_mantenimiento.xlsx"
    wb.save(response)
    return response
