"""Pruebas de ``auditar_cambios`` sobre el formulario de Empresa.

Las tres pruebas del campo secreto (``smtp_password``) **no** están aquí: se
mudaron a ``test_correo.py`` junto con los campos SMTP, que salieron de
``ConfiguracionForm``. La tercera de ellas tenía solo aserciones negativas y
habría pasado en falso verde al quedarse sin el campo que vigilaba, así que allí
lleva además una aserción positiva.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from .auditoria import auditar_cambios
from .forms import ConfiguracionForm
from .models import ConfiguracionSistema, RegistroAuditoria


def _datos(config, **cambios):
    datos = {
        "nombre_empresa": config.nombre_empresa,
        "nit": config.nit,
        "direccion": config.direccion,
        "telefono": config.telefono,
        "email_contacto": config.email_contacto,
        "pie_firma_reporte": config.pie_firma_reporte,
        "acta_mant_codigo": config.acta_mant_codigo,
        "acta_mant_version": config.acta_mant_version,
    }
    datos.update(cambios)
    return datos


class AuditarCambiosTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="aud", password="x")
        self.config = ConfiguracionSistema.objects.create(
            nombre_empresa="REDIHOS S.A.S", telefono="111",
        )

    def _form(self, **cambios):
        form = ConfiguracionForm(_datos(self.config, **cambios), instance=self.config)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        return form

    def test_registra_un_renglon_por_campo_cambiado(self):
        form = self._form(nombre_empresa="Clinica X", telefono="222")
        self.assertEqual(auditar_cambios(self.user, form), 2)
        detalles = list(RegistroAuditoria.objects.values_list("detalle", flat=True))
        self.assertEqual(len(detalles), 2)
        self.assertTrue(any("REDIHOS S.A.S" in d and "Clinica X" in d for d in detalles))
        registro = RegistroAuditoria.objects.first()
        self.assertEqual(registro.accion, "configurar")
        self.assertEqual(registro.modulo, "administracion")

    def test_un_form_sin_cambios_no_escribe_nada(self):
        form = self._form()
        self.assertEqual(auditar_cambios(self.user, form), 0)
        self.assertFalse(RegistroAuditoria.objects.filter(accion="configurar").exists())

    def test_usa_la_etiqueta_del_campo_no_su_nombre_tecnico(self):
        form = self._form(nombre_empresa="Clinica X")
        auditar_cambios(self.user, form)
        detalle = RegistroAuditoria.objects.get().detalle
        self.assertIn("Nombre de la empresa", detalle)
        self.assertNotIn("nombre_empresa", detalle)

    def test_un_valor_largo_se_recorta_a_100_caracteres(self):
        form = self._form(direccion="x" * 150)
        auditar_cambios(self.user, form)
        detalle = RegistroAuditoria.objects.get().detalle
        self.assertIn("x" * 100, detalle)
        self.assertNotIn("x" * 101, detalle)
