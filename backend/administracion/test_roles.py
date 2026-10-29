"""Pruebas de la matriz de permisos en base de datos y de su resolvedor único."""

from pathlib import Path
from unittest import mock
from unittest.mock import patch

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import OperationalError, ProgrammingError
from django.test import TestCase

from accounts.permisos import MODULOS, PERMISOS_POR_ROL, nivel_permiso
from administracion.models import PermisoRol, Rol
from administracion.registro import invalidar_cache, modulos_activos, nivel_de, roles_choices


class ResolvedorPermisosTests(TestCase):
    def setUp(self):
        # La caché sobrevive al rollback de cada prueba: se limpia antes y
        # después para no filtrar estado entre pruebas.
        invalidar_cache()
        self.addCleanup(invalidar_cache)

    def test_superadmin_siempre_escritura_en_todo(self):
        PermisoRol.objects.all().delete()
        invalidar_cache()
        activos = modulos_activos()
        self.assertTrue(activos, "sin módulos activos esta prueba no comprobaría nada")
        for modulo in MODULOS:
            if modulo not in activos:
                continue  # un módulo apagado gana sobre superadmin: se prueba aparte
            self.assertEqual(nivel_permiso("superadmin", modulo), "escritura")

    def test_no_se_le_puede_quitar_escritura_a_superadmin(self):
        """La llave de repuesto no se puede tirar: anti-meta 1 de la spec."""
        rol = Rol.objects.get(clave="superadmin")
        PermisoRol.objects.filter(rol=rol, modulo="administracion").update(nivel="ninguno")
        invalidar_cache()
        self.assertEqual(nivel_permiso("superadmin", "administracion"), "escritura")

    def test_la_matriz_sembrada_reproduce_la_del_codigo(self):
        for rol, permisos in PERMISOS_POR_ROL.items():
            for modulo, nivel in permisos.items():
                if modulo in ("licencias", "prestamos"):
                    continue  # modulos inactivos: resuelven a ninguno, se prueba aparte
                self.assertEqual(nivel_permiso(rol, modulo), nivel, f"{rol}/{modulo}")

    def test_un_cambio_en_la_matriz_se_refleja(self):
        self.assertEqual(nivel_permiso("tecnico", "documentos"), "lectura")
        PermisoRol.objects.filter(rol__clave="tecnico", modulo="documentos").update(nivel="escritura")
        invalidar_cache()
        self.assertEqual(nivel_permiso("tecnico", "documentos"), "escritura")

    def test_un_modulo_inactivo_resuelve_a_ninguno_para_todos(self):
        for rol in ("superadmin", "admin", "tecnico", "lectura"):
            self.assertEqual(nivel_permiso(rol, "licencias"), "ninguno")

    def test_un_rol_desconocido_resuelve_a_ninguno(self):
        self.assertEqual(nivel_permiso("rol_borrado", "inventario"), "ninguno")

    def test_con_la_tabla_vacia_se_usa_la_matriz_del_codigo(self):
        PermisoRol.objects.all().delete()
        invalidar_cache()
        # El respaldo es un fallo abierto, así que deja traza en el log.
        with self.assertLogs("administracion.registro", level="WARNING"):
            self.assertEqual(nivel_permiso("tecnico", "inventario"), "escritura")
            self.assertEqual(nivel_permiso("tecnico", "passwords"), "ninguno")

    def test_un_rol_de_sistema_no_se_puede_borrar(self):
        with self.assertRaises(ValidationError):
            Rol.objects.get(clave="superadmin").delete()
        self.assertTrue(Rol.objects.filter(clave="superadmin").exists())

    def test_la_matriz_completa_se_lee_en_una_sola_consulta(self):
        """El menú pregunta nueve veces por request: no puede ser una consulta por celda."""
        with self.assertNumQueries(1):
            for rol in ("superadmin", "admin", "tecnico", "lectura"):
                for modulo in MODULOS:
                    nivel_de(rol, modulo)

    def test_la_lectura_repetida_no_vuelve_a_consultar_la_base(self):
        nivel_de("tecnico", "inventario")  # llena la caché
        with self.assertNumQueries(0):
            self.assertEqual(nivel_de("tecnico", "inventario"), "escritura")

    def test_guardar_un_permiso_invalida_la_cache_por_senal(self):
        self.assertEqual(nivel_de("tecnico", "documentos"), "lectura")
        permiso = PermisoRol.objects.get(rol__clave="tecnico", modulo="documentos")
        permiso.nivel = "escritura"
        permiso.save()
        self.assertEqual(nivel_de("tecnico", "documentos"), "escritura")

    def test_la_tabla_vacia_queda_registrada(self):
        """Vaciar la tabla devuelve permisos de más: no puede pasar en silencio."""
        PermisoRol.objects.all().delete()
        invalidar_cache()
        with self.assertLogs("administracion.registro", level="WARNING") as registros:
            self.assertEqual(nivel_de("tecnico", "inventario"), "escritura")
        self.assertEqual(registros.records[0].levelname, "WARNING")

    def test_un_error_de_base_devuelve_la_matriz_del_codigo_y_queda_registrado(self):
        """Una migración a medias no puede tumbar todas las vistas, pero deja traza."""
        with self.assertLogs("administracion.registro", level="WARNING") as registros:
            with mock.patch(
                "administracion.registro.PermisoRol.objects.values_list",
                side_effect=OperationalError("no such table"),
            ):
                self.assertEqual(nivel_de("tecnico", "inventario"), "escritura")
        registro = registros.records[0]
        self.assertEqual(registro.levelname, "WARNING")
        # exc_info lleva el error original: sin él no se sabría qué falló.
        self.assertIsInstance(registro.exc_info[1], OperationalError)

    def test_la_respuesta_de_respaldo_no_se_guarda_en_cache(self):
        """Si se cacheara, sembrar filas sin señales (migración) congelaría el respaldo."""
        PermisoRol.objects.all().delete()
        with self.assertLogs("administracion.registro", level="WARNING"):
            self.assertEqual(nivel_de("tecnico", "passwords"), "ninguno")
        rol = Rol.objects.get(clave="tecnico")
        PermisoRol.objects.bulk_create([
            PermisoRol(rol=rol, modulo="passwords", nivel="escritura"),
        ])  # bulk_create no dispara post_save
        self.assertEqual(nivel_de("tecnico", "passwords"), "escritura")


class ChoicesDeRolTests(TestCase):
    def setUp(self):
        invalidar_cache()
        self.addCleanup(invalidar_cache)

    def test_los_choices_salen_de_la_tabla(self):
        Rol.objects.create(clave="auditor", nombre="Auditor externo", es_sistema=False, orden=50)
        invalidar_cache()
        self.assertIn(("auditor", "Auditor externo"), roles_choices())

    def test_sin_tabla_los_choices_son_los_cuatro_de_siempre(self):
        """`choices` llamable no puede reventar migrate sobre una base sin la tabla."""
        with patch("administracion.registro.Rol.objects") as objetos:
            objetos.all.side_effect = ProgrammingError("no existe la relacion")
            claves = [c for c, _ in roles_choices()]
        self.assertEqual(claves, ["superadmin", "admin", "tecnico", "lectura"])

    def test_los_choices_sembrados_son_los_cuatro_de_siempre(self):
        self.assertEqual(
            [c for c, _ in roles_choices()],
            ["superadmin", "admin", "tecnico", "lectura"],
        )

    def test_borrar_un_rol_lo_quita_de_los_choices_por_senal(self):
        Rol.objects.create(clave="auditor", nombre="Auditor externo", es_sistema=False, orden=50)
        self.assertIn(("auditor", "Auditor externo"), roles_choices())
        Rol.objects.get(clave="auditor").delete()
        self.assertNotIn(("auditor", "Auditor externo"), roles_choices())


class PuntoUnicoDeLecturaTests(TestCase):
    def test_nadie_lee_PERMISOS_POR_ROL_fuera_del_resolvedor(self):
        """Si vuelve a haber una lectura directa, el apagado de modulos se la salta."""
        permitidos = {
            "accounts/permisos.py",
            "accounts/tests.py",
            "administracion/test_roles.py",
            # El resolvedor son dos piezas: nivel_permiso (accounts/permisos.py)
            # y el motor cacheado (nivel_de), que necesita el dict como respaldo
            # para la tabla vacía. Leerlo ahí no se salta nada, porque el
            # apagado de módulos se aplica antes, en nivel_permiso.
            "administracion/registro.py",
        }
        raiz = Path(settings.BASE_DIR)
        infractores = []
        for archivo in raiz.rglob("*.py"):
            rel = archivo.relative_to(raiz).as_posix()
            # La migración de datos tiene que leer el dict para sembrar las 40
            # filas: es su único uso legítimo fuera del resolvedor.
            if rel in permitidos or rel.startswith("administracion/migrations/"):
                continue
            if "PERMISOS_POR_ROL" in archivo.read_text(encoding="utf-8"):
                infractores.append(rel)
        self.assertEqual(
            sorted(infractores),
            [],
            "Estos archivos leen PERMISOS_POR_ROL directamente; deben usar nivel_permiso().",
        )
