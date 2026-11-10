"""Runner de pruebas que aísla de la instalación lo que la suite ve y escribe.

Aísla dos cosas, y las dos salieron de rojos reales que **solo aparecían dentro
del contenedor de producción**, el único entorno donde la suite ve
`settings/production.py`.

**1. `MEDIA_ROOT`.** En el `media` de producción había 94 archivos sin
referenciar: 87 eran basura de las pruebas —15 de 8 bytes (`b"%PDF-1.4"`) y 72
de 9 bytes (`b"contenido"`), los literales de `documentos/tests.py:58` y `:27`—,
una copia por cada ejecución de la suite. `documentos/tests.py`,
`mantenimiento/tests.py` y `mantenimiento/test_robustez.py` suben archivos de
verdad sin redefinir `MEDIA_ROOT`. Y no es un detalle de desarrollo: la receta
de verificación de `GUIA_DEPLOY_PASO_A_PASO.md` §8b manda correr la suite dentro
del contenedor de producción, así que el propio paso de verificación ensuciaba
los datos que iba a verificar.

**2. `MEDIA_ACCEL_REDIRECT`.** Vale `False` en `base.py` y `True` en
`production.py`. Con `True`, `core.views.media_protegido` devuelve un
`HttpResponse` vacío con `X-Accel-Redirect` —el archivo lo sirve nginx— en vez
de un `FileResponse`, así que toda prueba que lea `streaming_content` revienta
con `AttributeError`. Pasó con `core.tests.MediaProtegidoTests` (2026-11-05) y
otra vez con `mantenimiento/test_acta_firmada.py:87` (2026-11-10). La primera se
parcheó prueba por prueba; la segunda demostró que eso no escala.

En los dos casos la alternativa era pedirle a cada prueba que recuerde un
`override_settings`, que es la misma disciplina a mano que ya falló con la lista
de modelos de `limpiar_historial`: tres archivos se la olvidaron. Aquí se fija
una vez para toda la suite. Una prueba que quiera el camino de nginx lo pide
explícitamente, como `core.tests.MediaProtegidoTests.test_x_accel_redirect_en_produccion`.

Lo vigila `core.tests.AislamientoDeLaSuiteTests`.
"""

import shutil
import tempfile
from pathlib import Path

from django.conf import settings
from django.test.runner import DiscoverRunner


class RunnerAislado(DiscoverRunner):
    """``DiscoverRunner`` que fija los settings de `media` para toda la suite."""

    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        self._aislar_settings()

    def teardown_test_environment(self, **kwargs):
        self._restaurar_settings()
        super().teardown_test_environment(**kwargs)

    # `_aislar_settings` / `_restaurar_settings` están separados del
    # setup/teardown de Django a propósito: así se pueden probar sin montar el
    # entorno de pruebas entero, que no se puede montar dos veces.
    def _aislar_settings(self):
        # `Path` y no `str`: hay código que hace `Path(settings.MEDIA_ROOT)` y
        # otro que lo usa con `/`, así que se conserva el tipo del original.
        self._media_temporal = Path(tempfile.mkdtemp(prefix="sysadmin-pruebas-media-"))
        self._original = {
            "MEDIA_ROOT": settings.MEDIA_ROOT,
            "MEDIA_ACCEL_REDIRECT": getattr(settings, "MEDIA_ACCEL_REDIRECT", False),
        }
        settings.MEDIA_ROOT = self._media_temporal
        settings.MEDIA_ACCEL_REDIRECT = False

    def _restaurar_settings(self):
        # Se restaura antes de borrar, para que un fallo al borrar no deje los
        # settings apuntando a una carpeta que ya no existe.
        for nombre, valor in self._original.items():
            setattr(settings, nombre, valor)
        shutil.rmtree(self._media_temporal, ignore_errors=True)
