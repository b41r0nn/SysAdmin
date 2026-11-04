def acotado(valor, minimo, maximo, etiqueta, avisar):
    """Acota al rango ``[minimo, maximo]`` un número que viene de la base de datos.

    Es la capa que de verdad cierra los desbordamientos de la configuración y no
    se puede sustituir por los validadores del campo: ``queryset.update()`` y un
    ``UPDATE`` por SQL no corren ``save()`` ni ``full_clean()``, así que la fila
    puede contener cualquier entero positivo. Y con esos números el sistema no
    se pone «muy permisivo», se cae: un ``now() - timedelta(...)`` desbordado es
    un 500 en cada intento de login (``administracion.seguridad``) o un cron de
    limpieza que muere sin purgar nada
    (``core.management.commands.limpiar_historial``).

    Es el mismo principio que ``accounts.permisos.modulos_activos()`` con
    ``MODULOS_ESENCIALES`` y que ``nivel_permiso`` con el superadministrador: la
    decisión sale de una constante de código, no del dato.

    Vive aquí, en una sola función, porque lo delicado es el borde: el tope es el
    último valor **aceptable**, y un ``>`` donde va un ``>=`` cambiaría la
    política sin que nada falle.

    ``avisar`` es el sink del aviso y se inyecta porque los dos llamadores tienen
    uno distinto: ``logger.warning`` en la política de seguridad y
    ``self.stderr.write`` en el comando de limpieza, que el cron recoge en su log
    (un ``logger.warning`` ahí dejaría el aviso dos veces y parecería que falló
    dos veces).

    El mensaje está redactado **sin concordancia de género**: la etiqueta la pone
    el llamador y puede ser «los minutos de sesión» o «las horas de bloqueo».

    El ``None`` se trata aparte porque las columnas son ``NOT NULL`` hoy, pero un
    ``None`` llegando aquí daría un ``TypeError`` en la comparación, es decir el
    mismo 500 que se está evitando.
    """
    if valor is None or valor < minimo:
        avisar(
            f"Valor fuera de rango en {etiqueta} ({valor!r}); "
            f"se usa el mínimo de {minimo}."
        )
        return minimo
    if valor > maximo:
        avisar(
            f"Valor fuera de rango en {etiqueta} ({valor!r}); "
            f"se usa el máximo de {maximo}."
        )
        return maximo
    return valor


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
