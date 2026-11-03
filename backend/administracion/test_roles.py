"""Pruebas de la matriz de permisos en base de datos y de su resolvedor único."""

from pathlib import Path
from unittest import mock
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import OperationalError, ProgrammingError
from django.test import TestCase
from django.urls import reverse

from accounts.permisos import MODULOS, PERMISOS_POR_ROL, nivel_permiso
from administracion.models import Modulo, PermisoRol, RegistroAuditoria, Rol
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

    def test_al_superadmin_no_se_le_puede_guardar_otro_nivel(self):
        """La guarda de la llave de repuesto, en el modelo y no solo en la vista.

        La validación de la pantalla de roles no se hereda: una importación
        masiva, un comando de gestión o un ``ModelForm`` futuro guardan por
        instancia y no pasan por ella. Aquí sí.
        """
        for modulo in MODULOS:
            for nivel in ("ninguno", "lectura"):
                with self.subTest(modulo=modulo, nivel=nivel):
                    permiso = PermisoRol.objects.get(rol__clave="superadmin", modulo=modulo)
                    permiso.nivel = nivel
                    with self.assertRaises(ValidationError) as contexto:
                        permiso.save()
                    self.assertIn("nivel", contexto.exception.message_dict)
                    permiso.refresh_from_db()
                    self.assertEqual(permiso.nivel, "escritura")

    def test_una_fila_nueva_del_superadmin_tampoco_nace_degradada(self):
        """La fila puede no existir (base a medias): al crearla, la misma regla."""
        rol = Rol.objects.get(clave="superadmin")
        PermisoRol.objects.filter(rol=rol, modulo="soporte").delete()
        with self.assertRaises(ValidationError) as contexto:
            PermisoRol(rol=rol, modulo="soporte", nivel="ninguno").save()
        self.assertIn("nivel", contexto.exception.message_dict)
        self.assertFalse(PermisoRol.objects.filter(rol=rol, modulo="soporte").exists())

    def test_al_superadmin_si_se_le_guarda_escritura(self):
        """Contraste: la guarda no puede bloquear el guardado legítimo."""
        rol = Rol.objects.get(clave="superadmin")
        permiso = PermisoRol.objects.get(rol=rol, modulo="administracion")
        permiso.nivel = "escritura"
        permiso.save()  # no lanza
        self.assertEqual(
            PermisoRol.objects.get(rol=rol, modulo="administracion").nivel, "escritura"
        )

        # Y una fila nueva con escritura también nace bien.
        PermisoRol.objects.filter(rol=rol, modulo="soporte").delete()
        PermisoRol(rol=rol, modulo="soporte", nivel="escritura").save()
        self.assertEqual(
            PermisoRol.objects.get(rol=rol, modulo="soporte").nivel, "escritura"
        )


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


class PantallaRolesTests(TestCase):
    """La matriz de roles × módulos que se edita celda a celda.

    Todas las pruebas de rechazo mandan el POST directo, sin pasar por el HTML:
    un ``<select>`` con tres opciones y una columna dibujada como texto fijo no
    son una validación. La validación vive en la vista (400) y en
    ``PermisoRol.save()`` (``full_clean()``).
    """

    def setUp(self):
        # La caché sobrevive al rollback de cada prueba: se limpia antes y
        # después para no filtrar estado entre pruebas.
        invalidar_cache()
        self.addCleanup(invalidar_cache)
        self.superadmin = get_user_model().objects.create_user(
            username="super_matriz", password="x", rol="superadmin"
        )
        self.client.force_login(self.superadmin)

    def crear_usuario(self, rol):
        return get_user_model().objects.create_user(
            username=f"matriz_{rol}", password="x", rol=rol
        )

    def guardar(self, rol, modulo, nivel, **extra):
        return self.client.post(
            reverse("administracion:guardar_permiso", args=[rol, modulo]),
            {"nivel": nivel},
            **extra,
        )

    def test_la_matriz_trae_todos_los_modulos_y_roles(self):
        resp = self.client.get(reverse("administracion:roles"))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "administracion/roles_matriz.html")
        self.assertEqual(Rol.objects.count(), 4)
        self.assertEqual(Modulo.objects.count(), 10)
        for rol in Rol.objects.all():
            with self.subTest(rol=rol.clave):
                self.assertContains(resp, rol.nombre)
        # Licencias y Préstamos nacen apagados y aun así salen: hay que poder
        # dejar los permisos listos ANTES de encender un módulo.
        self.assertFalse(Modulo.objects.get(clave="licencias").activo)
        self.assertFalse(Modulo.objects.get(clave="prestamos").activo)
        for modulo in Modulo.objects.all():
            with self.subTest(modulo=modulo.clave):
                self.assertContains(resp, modulo.nombre)
        # Las 30 celdas editables: los tres roles que no son superadmin.
        for clave_rol in ("admin", "tecnico", "lectura"):
            for clave_modulo in Modulo.objects.values_list("clave", flat=True):
                with self.subTest(celda=f"{clave_rol}/{clave_modulo}"):
                    self.assertContains(
                        resp,
                        reverse("administracion:guardar_permiso", args=[clave_rol, clave_modulo]),
                    )

    def test_guardar_una_celda_cambia_el_permiso(self):
        resp = self.client.post(
            reverse("administracion:guardar_permiso", args=["tecnico", "documentos"]),
            {"nivel": "escritura"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "administracion/partials/celda_permiso.html")
        self.assertTemplateNotUsed(resp, "base.html")
        self.assertEqual(nivel_permiso("tecnico", "documentos"), "escritura")
        self.assertEqual(
            PermisoRol.objects.get(rol__clave="tecnico", modulo="documentos").nivel,
            "escritura",
        )

    def test_la_columna_de_superadmin_sale_deshabilitada(self):
        resp = self.client.get(reverse("administracion:roles"))
        # Texto fijo en las diez filas y ni un control que apunte a la vista.
        self.assertContains(resp, "Escritura (fijo)", count=10)
        for clave_modulo in Modulo.objects.values_list("clave", flat=True):
            with self.subTest(modulo=clave_modulo):
                self.assertNotContains(
                    resp,
                    reverse("administracion:guardar_permiso", args=["superadmin", clave_modulo]),
                )

    def test_tocar_la_celda_de_superadmin_se_rechaza(self):
        """Foco de revision 1: la llave de repuesto no se toca ni por POST directo."""
        resp = self.guardar("superadmin", "administracion", "ninguno")
        self.assertEqual(resp.status_code, 400)
        # La fila guardada es la que manda: nivel_permiso responde "escritura"
        # para superadmin sin mirar la tabla, así que sola no probaría nada.
        self.assertEqual(
            PermisoRol.objects.get(rol__clave="superadmin", modulo="administracion").nivel,
            "escritura",
        )
        self.assertEqual(nivel_permiso("superadmin", "administracion"), "escritura")
        # Ni en ningún otro módulo, ni con un nivel que parezca inofensivo.
        for clave_modulo in Modulo.objects.values_list("clave", flat=True):
            for nivel in ("ninguno", "lectura", "escritura"):
                with self.subTest(modulo=clave_modulo, nivel=nivel):
                    self.assertEqual(
                        self.guardar("superadmin", clave_modulo, nivel).status_code, 400
                    )
        self.assertEqual(
            set(
                PermisoRol.objects.filter(rol__clave="superadmin").values_list("nivel", flat=True)
            ),
            {"escritura"},
        )
        self.assertFalse(RegistroAuditoria.objects.filter(accion="configurar").exists())

    def test_un_nivel_invalido_se_rechaza(self):
        for nivel in ("total", "", "LECTURA", "ninguno ", "admin"):
            with self.subTest(nivel=nivel):
                self.assertEqual(self.guardar("tecnico", "documentos", nivel).status_code, 400)
                self.assertEqual(
                    PermisoRol.objects.get(rol__clave="tecnico", modulo="documentos").nivel,
                    "lectura",
                )
        # Sin el campo tampoco: un POST vacío no puede valer como "ninguno".
        resp = self.client.post(
            reverse("administracion:guardar_permiso", args=["tecnico", "documentos"])
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(nivel_permiso("tecnico", "documentos"), "lectura")
        self.assertFalse(RegistroAuditoria.objects.filter(accion="configurar").exists())

    def test_el_cambio_surte_efecto_en_una_vista_de_inmediato(self):
        """Sin esperar los 300 s de la caché: se guarda por instancia y la señal la limpia."""
        tecnico = self.crear_usuario("tecnico")
        url = reverse("documentos:crear")  # exige escritura en documentos
        self.assertEqual(nivel_permiso("tecnico", "documentos"), "lectura")
        self.client.force_login(tecnico)
        self.assertEqual(self.client.get(url).status_code, 302)

        self.client.force_login(self.superadmin)
        self.assertEqual(self.guardar("tecnico", "documentos", "escritura").status_code, 200)

        self.client.force_login(tecnico)
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_el_cambio_queda_auditado_con_anterior_y_nuevo(self):
        self.guardar("tecnico", "documentos", "escritura")
        registro = RegistroAuditoria.objects.get(accion="configurar")
        self.assertEqual(registro.usuario, self.superadmin)
        self.assertEqual(registro.modulo, "administracion")
        self.assertEqual(registro.objeto_tipo, "permisorol")
        self.assertIn("Técnico", registro.detalle)
        self.assertIn("Documentos", registro.detalle)
        # El anterior y el nuevo, y en ese orden: "de Lectura a Escritura" y
        # "de Escritura a Lectura" no son el mismo cambio.
        self.assertIn("Lectura", registro.detalle)
        self.assertIn("Escritura", registro.detalle)
        self.assertLess(registro.detalle.index("Lectura"), registro.detalle.index("Escritura"))

    def test_un_tecnico_no_puede_abrir_la_matriz(self):
        self.client.force_login(self.crear_usuario("tecnico"))
        # administracion es "ninguno" para el técnico: redirige, no 404.
        self.assertEqual(self.client.get(reverse("administracion:roles")).status_code, 302)
        # Ni escribir en ella por POST directo, ni para subirse el permiso.
        self.assertEqual(self.guardar("tecnico", "documentos", "escritura").status_code, 302)
        self.assertEqual(
            PermisoRol.objects.get(rol__clave="tecnico", modulo="documentos").nivel,
            "lectura",
        )
        self.assertFalse(RegistroAuditoria.objects.filter(accion="configurar").exists())


class MatrizSoloLecturaTests(TestCase):
    """Quien solo tiene lectura no ve los ``<select>``, y su POST da 403, no 302.

    Con un 302, HTMX sigue la redirección de forma transparente y acaba
    intercambiando el tablero —o el formulario de login, si la sesión caducó—
    dentro del ``<td>`` que disparó la petición. Con un 403 no intercambia nada
    y el manejador de ``htmx:responseError`` avisa. No pintar el control evita
    además que el problema llegue a ocurrir.
    """

    def setUp(self):
        invalidar_cache()
        self.addCleanup(invalidar_cache)

    def entrar_con(self, nivel):
        """Deja el rol «admin» con ese nivel en administracion y entra con él.

        En la matriz de fábrica ningún rol tiene administracion distinto de
        «ninguno», pero «que vea la configuración sin cambiarla» es razonable y,
        desde que la matriz es editable, alcanzable por la interfaz.
        """
        PermisoRol.objects.filter(rol__clave="admin", modulo="administracion").update(nivel=nivel)
        invalidar_cache()
        self.client.force_login(
            get_user_model().objects.create_user(
                username=f"matriz_admin_{nivel}", password="x", rol="admin"
            )
        )

    def guardar(self, rol, modulo, nivel, **extra):
        return self.client.post(
            reverse("administracion:guardar_permiso", args=[rol, modulo]),
            {"nivel": nivel},
            **extra,
        )

    def test_con_solo_lectura_la_matriz_no_trae_selects(self):
        self.entrar_con("lectura")
        resp = self.client.get(reverse("administracion:roles"))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "<select")
        self.assertNotContains(resp, "hx-post")
        for clave_rol in ("admin", "tecnico", "lectura"):
            for clave_modulo in Modulo.objects.values_list("clave", flat=True):
                with self.subTest(celda=f"{clave_rol}/{clave_modulo}"):
                    self.assertNotContains(
                        resp,
                        reverse("administracion:guardar_permiso", args=[clave_rol, clave_modulo]),
                    )
        # La matriz se sigue viendo: deja de ser editable, no de informar.
        self.assertContains(resp, "Escritura (fijo)", count=10)
        self.assertContains(resp, "Lectura")

    def test_con_solo_lectura_el_post_por_htmx_responde_403(self):
        self.entrar_con("lectura")
        resp = self.guardar("tecnico", "documentos", "escritura", HTTP_HX_REQUEST="true")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(
            PermisoRol.objects.get(rol__clave="tecnico", modulo="documentos").nivel, "lectura"
        )
        self.assertFalse(RegistroAuditoria.objects.filter(accion="configurar").exists())

    def test_sin_la_cabecera_de_htmx_sigue_redirigiendo_como_hoy(self):
        """Regresión: una navegación normal no cambia."""
        self.entrar_con("lectura")
        self.assertEqual(self.guardar("tecnico", "documentos", "escritura").status_code, 302)
        self.assertEqual(
            PermisoRol.objects.get(rol__clave="tecnico", modulo="documentos").nivel, "lectura"
        )

    def test_con_escritura_la_matriz_sigue_siendo_editable(self):
        """Contraprueba: sin ella, no pintar los controles podría haber apagado
        la pantalla para todo el mundo sin que ninguna prueba se enterara."""
        self.entrar_con("escritura")
        resp = self.client.get(reverse("administracion:roles"))
        self.assertContains(resp, "<select", count=30)
        for clave_rol in ("admin", "tecnico", "lectura"):
            for clave_modulo in Modulo.objects.values_list("clave", flat=True):
                with self.subTest(celda=f"{clave_rol}/{clave_modulo}"):
                    self.assertContains(
                        resp,
                        reverse("administracion:guardar_permiso", args=[clave_rol, clave_modulo]),
                    )
        # Y el guardado por HTMX sigue funcionando.
        resp = self.guardar("tecnico", "documentos", "escritura", HTTP_HX_REQUEST="true")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            PermisoRol.objects.get(rol__clave="tecnico", modulo="documentos").nivel, "escritura"
        )

    def test_la_celda_que_devuelve_el_post_vuelve_con_su_select(self):
        """El parcial se pinta fuera del contexto de la pantalla: si no recibiera
        el permiso, el intercambio dejaría la celda sin ``<select>``."""
        self.entrar_con("escritura")
        resp = self.guardar("tecnico", "documentos", "escritura", HTTP_HX_REQUEST="true")
        self.assertContains(resp, "<select", count=1)
        self.assertContains(
            resp, reverse("administracion:guardar_permiso", args=["tecnico", "documentos"])
        )


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
