from unittest import mock

from django.core.exceptions import ValidationError
from django.db import OperationalError
from django.test import TestCase
from django.urls import reverse

from accounts.permisos import APP_A_MODULO, MODULOS
from administracion.models import Modulo
from administracion.registro import invalidar_cache, modulo_esta_activo, modulos_activos


class CatalogoModulosTests(TestCase):
    def setUp(self):
        # La caché (LocMemCache en local, FileBasedCache en producción) sobrevive
        # al rollback de cada prueba: se limpia antes y después para no filtrar
        # estado entre pruebas.
        invalidar_cache()
        self.addCleanup(invalidar_cache)

    def test_la_migracion_siembra_los_diez_modulos(self):
        self.assertEqual(Modulo.objects.count(), 10)
        self.assertEqual(set(Modulo.objects.values_list("clave", flat=True)), set(MODULOS))

    def test_licencias_y_prestamos_nacen_inactivos(self):
        self.assertFalse(Modulo.objects.get(clave="licencias").activo)
        self.assertFalse(Modulo.objects.get(clave="prestamos").activo)
        # los ocho restantes activos
        self.assertEqual(Modulo.objects.filter(activo=True).count(), 8)

    def test_los_esenciales_son_los_cuatro_esperados(self):
        esenciales = set(Modulo.objects.filter(es_esencial=True).values_list("clave", flat=True))
        self.assertEqual(esenciales, {"inventario", "mantenimiento", "passwords", "administracion"})

    def test_un_modulo_esencial_no_se_puede_desactivar(self):
        modulo = Modulo.objects.get(clave="administracion")
        modulo.activo = False
        with self.assertRaises(ValidationError):
            modulo.save()
        self.assertTrue(Modulo.objects.get(clave="administracion").activo)

    def test_todo_modulo_tiene_url_resoluble(self):
        for modulo in Modulo.objects.all():
            reverse(modulo.url_nombre)  # no debe lanzar NoReverseMatch

    def test_con_la_tabla_vacia_todo_se_considera_activo(self):
        """Base nueva o migración a medias no puede esconder la aplicación."""
        Modulo.objects.all().delete()
        invalidar_cache()
        for clave in MODULOS:
            self.assertTrue(modulo_esta_activo(clave))

    def test_una_clave_desconocida_no_esta_activa(self):
        self.assertFalse(modulo_esta_activo("inventado"))

    def test_guardar_un_modulo_invalida_la_cache(self):
        self.assertTrue(modulo_esta_activo("soporte"))
        Modulo.objects.filter(clave="soporte").update(activo=False)
        invalidar_cache()
        self.assertFalse(modulo_esta_activo("soporte"))

    def test_cada_app_del_urlconf_mapea_a_un_modulo_conocido(self):
        for clave in APP_A_MODULO.values():
            self.assertIn(clave, MODULOS)

    def test_las_apps_con_nombre_distinto_al_del_modulo_se_mapean(self):
        self.assertEqual(APP_A_MODULO["reports"], "reportes")
        self.assertEqual(APP_A_MODULO["yule"], "inventario")
        for clave in MODULOS:
            self.assertEqual(APP_A_MODULO[clave], clave)


class CacheDeModulosTests(TestCase):
    """El guardado y el borrado de un módulo vacían la caché por señal."""

    def setUp(self):
        invalidar_cache()
        self.addCleanup(invalidar_cache)

    def test_save_invalida_la_cache_sin_llamar_a_invalidar_cache(self):
        self.assertIn("documentos", modulos_activos())
        modulo = Modulo.objects.get(clave="documentos")
        modulo.activo = False
        modulo.save()
        self.assertNotIn("documentos", modulos_activos())

    def test_delete_invalida_la_cache_sin_llamar_a_invalidar_cache(self):
        self.assertIn("documentos", modulos_activos())
        Modulo.objects.get(clave="documentos").delete()
        self.assertNotIn("documentos", modulos_activos())

    def test_la_lectura_repetida_no_vuelve_a_consultar_la_base(self):
        modulos_activos()  # llena la caché
        with self.assertNumQueries(0):
            self.assertEqual(modulos_activos(), modulos_activos())

    def test_un_error_de_base_devuelve_todos_los_modulos_y_queda_registrado(self):
        """Una migración a medias no puede tumbar el login, pero el fallo abierto deja traza."""
        with self.assertLogs("administracion.registro", level="WARNING") as registros:
            with mock.patch(
                "administracion.registro.Modulo.objects.values_list",
                side_effect=OperationalError("no such table"),
            ):
                self.assertEqual(modulos_activos(), set(MODULOS))
        self.assertEqual(len(registros.records), 1)
        registro = registros.records[0]
        self.assertEqual(registro.levelname, "WARNING")
        # exc_info lleva el error original: sin él no se sabría qué falló.
        self.assertIsInstance(registro.exc_info[1], OperationalError)

    def test_la_respuesta_de_tabla_vacia_no_se_guarda_en_cache(self):
        """Si se cacheara, sembrar filas sin señales (migración) dejaría todo activo."""
        Modulo.objects.all().delete()
        self.assertEqual(modulos_activos(), set(MODULOS))
        Modulo.objects.bulk_create([
            Modulo(clave="soporte", nombre="Soporte", icono="bi-life-preserver",
                   url_nombre="soporte:lista", orden=80, activo=True),
        ])  # bulk_create no dispara post_save
        self.assertEqual(modulos_activos(), {"soporte"})
