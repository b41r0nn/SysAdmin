from django.contrib.auth import get_user_model
from django.test import TestCase

from .auditoria import auditar_cambios
from .forms import ConfiguracionForm
from .models import ConfiguracionSistema, RegistroAuditoria

SECRETO = "Sup3rS3cr3ta!"


def _datos(config, **cambios):
    datos = {
        "nombre_empresa": config.nombre_empresa,
        "nit": config.nit,
        "direccion": config.direccion,
        "telefono": config.telefono,
        "email_contacto": config.email_contacto,
        "pie_firma_reporte": config.pie_firma_reporte,
        "smtp_host": config.smtp_host,
        "smtp_puerto": config.smtp_puerto,
        "smtp_usuario": config.smtp_usuario,
        "acta_mant_codigo": config.acta_mant_codigo,
        "acta_mant_version": config.acta_mant_version,
    }
    if config.smtp_usa_tls:
        datos["smtp_usa_tls"] = "on"
    if config.smtp_usa_ssl:
        datos["smtp_usa_ssl"] = "on"
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

    def test_un_campo_declarado_secreto_se_registra_sin_su_valor(self):
        form = self._form(smtp_password=SECRETO)
        self.assertEqual(auditar_cambios(self.user, form, secretos=("smtp_password",)), 1)
        detalles = " ".join(RegistroAuditoria.objects.values_list("detalle", flat=True))
        self.assertNotIn(SECRETO, detalles)
        self.assertIn("(cambiada)", detalles)
        self.assertIn("Contraseña SMTP", detalles)

    def test_ningun_registro_de_auditoria_contiene_el_secreto_en_claro(self):
        form = self._form(smtp_password=SECRETO, telefono="333")
        auditar_cambios(self.user, form, secretos=("smtp_password",), ip="10.0.0.1")
        self.assertEqual(RegistroAuditoria.objects.count(), 2)
        for registro in RegistroAuditoria.objects.all():
            for campo in registro._meta.get_fields():
                if not getattr(campo, "concrete", False) or campo.is_relation:
                    continue
                self.assertNotIn(SECRETO, str(getattr(registro, campo.name)), campo.name)

    def test_el_secreto_anterior_tampoco_entra_en_el_texto(self):
        self.config.set_smtp_password(SECRETO)
        self.config.save()
        form = self._form(smtp_password="Otra#Clave9")
        auditar_cambios(self.user, form, secretos=("smtp_password",))
        detalles = " ".join(RegistroAuditoria.objects.values_list("detalle", flat=True))
        self.assertNotIn(SECRETO, detalles)
        self.assertNotIn("Otra#Clave9", detalles)
