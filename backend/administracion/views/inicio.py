from django.contrib.auth import get_user_model
from django.shortcuts import render
from django.urls import reverse

from accounts.permisos import requiere_permiso
from notificaciones.models import NotificacionEmail

from ..models import ConfiguracionSistema, Modulo, Rol


def _plural(cantidad, singular, plural):
    return f"{cantidad} {singular if cantidad == 1 else plural}"


@requiere_permiso("administracion", "lectura")
def inicio(request):
    """Portada de Configuración: una tarjeta por área, con su conteo vivo."""
    Cuenta = get_user_model()
    total_cuentas = Cuenta.objects.count()
    cuentas_activas = Cuenta.objects.filter(is_active=True).count()
    total_modulos = Modulo.objects.count()
    modulos_activos = Modulo.objects.filter(activo=True).count()

    sin_enviar = NotificacionEmail.objects.filter(enviado=False)
    pendientes = sin_enviar.count()
    con_error = sin_enviar.exclude(error="").count()

    ultimo_cambio = ConfiguracionSistema.get_config().fecha_actualizacion

    areas = [
        {
            "clave": "empresa",
            "titulo": "Empresa",
            "icono": "bi-building",
            "descripcion": "Datos de la empresa que salen en reportes y actas.",
            "url": reverse("administracion:configuracion"),
            "resumen": "",
        },
        {
            "clave": "cuentas",
            "titulo": "Cuentas",
            "icono": "bi-people",
            "descripcion": "Quién entra al sistema y con qué rol.",
            "url": reverse("administracion:cuentas"),
            "resumen": f"{cuentas_activas} activas de {total_cuentas}",
        },
        {
            "clave": "auditoria",
            "titulo": "Auditoría",
            "icono": "bi-journal-text",
            "descripcion": "Registro de quién cambió qué y cuándo.",
            "url": reverse("administracion:lista_auditoria"),
            "resumen": "",
        },
        {
            "clave": "modulos",
            "titulo": "Módulos",
            "icono": "bi-grid-3x3-gap",
            "descripcion": "Qué partes del sistema están encendidas.",
            "url": reverse("administracion:modulos"),
            "resumen": f"{modulos_activos} de {total_modulos} activos",
        },
        {
            "clave": "roles",
            "titulo": "Roles y permisos",
            "icono": "bi-shield-check",
            "descripcion": "Qué puede ver y hacer cada rol en cada módulo.",
            "url": reverse("administracion:roles"),
            "resumen": _plural(Rol.objects.count(), "rol", "roles"),
        },
        {
            "clave": "correo",
            "titulo": "Correo",
            "icono": "bi-envelope",
            "descripcion": "Servidor SMTP, remitente y cola de envíos.",
            "url": reverse("administracion:correo"),
            "resumen": (
                f"{_plural(pendientes, 'pendiente', 'pendientes')} · {con_error} con error"
            ),
            "alerta": con_error > 0,
        },
        {
            "clave": "seguridad",
            "titulo": "Seguridad",
            "icono": "bi-lock",
            "descripcion": "Intentos de acceso, bloqueo y sesiones.",
            "url": reverse("administracion:seguridad"),
            "resumen": "",
        },
        {
            "clave": "datos",
            "titulo": "Datos",
            "icono": "bi-database",
            "descripcion": "Retención y limpieza de registros antiguos.",
            "url": reverse("administracion:datos"),
            "resumen": "",
        },
        {
            "clave": "yule",
            "titulo": "Yule / OCS",
            "icono": "bi-hdd-network",
            "descripcion": "Conexión con el inventario automático de OCS.",
            "url": reverse("yule:configuracion"),
            "resumen": "",
        },
    ]
    return render(request, "administracion/inicio.html", {
        "areas": areas,
        "ultimo_cambio": ultimo_cambio,
    })
