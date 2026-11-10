"""Runner de pruebas que aísla lo que la suite escribe en disco.

Existe por una auditoría del 2026-11-10: en el `media` de **producción** había
94 archivos basura —87 `manual.pdf`, `manual_1PtyvqN.pdf`, `manual_1U0infs.pdf`…
y 7 en `inventario/actas/firmadas`— con los nombres que Django inventa cuando el
archivo ya existe. Los dejaban `documentos/tests.py`, `mantenimiento/tests.py` y
`mantenimiento/test_robustez.py`, que suben archivos de verdad sin redefinir
`MEDIA_ROOT`: una copia por cada ejecución de la suite.

Y no era un detalle de desarrollo: la receta de verificación de
`GUIA_DEPLOY_PASO_A_PASO.md` manda correr la suite **dentro del contenedor de
producción**, que es el único entorno donde se ven los settings de producción.
El propio paso de verificación ensuciaba los datos que iba a verificar.

El aislamiento va aquí, en el runner, y no en un `override_settings` por prueba,
porque acordarse archivo por archivo es la misma disciplina a mano que ya falló
con la lista de modelos de `limpiar_historial`: tres archivos se la olvidaron.
`core.tests.AislamientoDeLaSuiteTests` vigila que siga puesto.
"""

import shutil
import tempfile
from pathlib import Path

from django.conf import settings
from django.test.runner import DiscoverRunner


class RunnerAislado(DiscoverRunner):
    """``DiscoverRunner`` con un ``MEDIA_ROOT`` propio y desechable."""

    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        # `Path` y no `str`: hay código que hace `Path(settings.MEDIA_ROOT)` y
        # otro que lo usa con `/`, así que se conserva el tipo del original.
        self._media_temporal = Path(tempfile.mkdtemp(prefix="sysadmin-pruebas-media-"))
        self._media_original = settings.MEDIA_ROOT
        settings.MEDIA_ROOT = self._media_temporal

    def teardown_test_environment(self, **kwargs):
        # Se restaura antes de borrar, para que un fallo al borrar no deje los
        # settings apuntando a una carpeta que ya no existe.
        settings.MEDIA_ROOT = self._media_original
        shutil.rmtree(self._media_temporal, ignore_errors=True)
        super().teardown_test_environment(**kwargs)
