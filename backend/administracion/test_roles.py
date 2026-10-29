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


class ValidacionAlGuardarTests(TestCase):
    """``save()`` valida: la regla vive en el modelo y no en un formulario.

    Sin ``full_clean()`` un ``nivel`` fuera de ``NIVEL_CHOICES`` llegaría a la
    tabla, y ``tiene_permiso()`` lo trataría como una lectura concedida.
    """

    def setUp(self):
        # Crear un Rol dispara la señal que limpia la caché, y esa caché
        # sobrevive al rollback de cada prueba.
        invalidar_cache()
        self.addCleanup(invalidar_cache)

    def test_rol_save_ejecuta_validacion(self):
        rol = Rol(clave="", nombre="Sin clave", es_sistema=False, orden=60)
        with self.assertRaises(ValidationError) as contexto:
            rol.save()
        self.assertIn("clave", contexto.exception.message_dict)
        self.assertFalse(Rol.objects.filter(nombre="Sin clave").exists())

    def test_permiso_rol_nivel_invalido_no_se_guarda(self):
        rol = Rol.objects.create(clave="auditor", nombre="Auditor externo", es_sistema=False, orden=50)
        permiso = PermisoRol(rol=rol, modulo="inventario", nivel="basura")
        with self.assertRaises(ValidationError) as contexto:
            permiso.save()
        self.assertIn("nivel", contexto.exception.message_dict)
        self.assertFalse(PermisoRol.objects.filter(rol=rol).exists())


class SiembraDeFabricaTests(TestCase):
    def test_la_migracion_siembra_las_40_celdas_de_fabrica(self):
        """Lee la tabla tal cual, sin pasar por el resolvedor.

        ``test_la_matriz_sembrada_reproduce_la_del_codigo`` pasa por
        ``nivel_permiso``: no ve las celdas de licencias y préstamos (módulos
        apagados) y, con la tabla vacía, responde con el dict del código y
        pasaría igual. La migración 0008 lleva su propia copia congelada de la
        matriz; esta prueba es la que detecta una errata en esa copia.
        """
        sembradas = {
            (rol, modulo): nivel
            for rol, modulo, nivel in PermisoRol.objects.values_list("rol__clave", "modulo", "nivel")
        }
        de_fabrica = {
            (rol, modulo): nivel
            for rol, permisos in PERMISOS_POR_ROL.items()
            for modulo, nivel in permisos.items()
        }
        self.assertEqual(len(de_fabrica), 40)
        self.assertEqual(PermisoRol.objects.count(), 40)
        # Solo las celdas que difieren: con 40 pares, el diff completo de dos
        # diccionarios sale truncado y no dice cuál es la errata.
        diferencias = {
            celda: {"tabla": sembradas.get(celda), "codigo": de_fabrica.get(celda)}
            for celda in sembradas.keys() | de_fabrica.keys()
            if sembradas.get(celda) != de_fabrica.get(celda)
        }
        self.assertEqual(diferencias, {}, "Celdas (rol, módulo) donde la tabla no coincide con el código.")


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
            # Las migraciones tampoco están exentas: la 0008 siembra desde una
            # copia congelada de las 40 celdas. Si importara el dict en vivo,
            # `migrate` sobre una base nueva fallaría el día que el dict cambie
            # o se borre.
            if rel in permitidos:
                continue
            if "PERMISOS_POR_ROL" in archivo.read_text(encoding="utf-8"):
                infractores.append(rel)
        self.assertEqual(
            sorted(infractores),
            [],
            "Estos archivos leen PERMISOS_POR_ROL directamente; deben usar nivel_permiso().",
        )
