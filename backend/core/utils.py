def get_client_ip(request):
    """IP real del cliente detrás de nginx.

    nginx fija X-Forwarded-For = $remote_addr. Se toma el ÚLTIMO valor (el que
    agregó nuestro proxy), nunca el primero, que el cliente puede falsificar.
    Sin proxy (desarrollo) cae a REMOTE_ADDR.
    """
    if not request or not getattr(request, "META", None):
        return None
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        return xff.split(",")[-1].strip() or request.META.get("REMOTE_ADDR")
    return request.META.get("REMOTE_ADDR")


def guardar_excel(wb, destino):
    """Guarda un workbook de openpyxl sin fórmulas en las celdas.

    openpyxl convierte cualquier texto que empiece por "=" en una fórmula, así
    que un dato capturado por un usuario (p. ej. "=HYPERLINK(...)") se
    ejecutaría al abrir el reporte en Excel. Los exportes no usan fórmulas
    propias: toda celda marcada como fórmula se guarda como texto.
    """
    for ws in wb.worksheets:
        for fila in ws.iter_rows():
            for celda in fila:
                if celda.data_type == "f":
                    celda.data_type = "s"
    wb.save(destino)
