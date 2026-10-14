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
