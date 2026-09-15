import logging

from yule.client import build_client, OCSClientException

logger = logging.getLogger(__name__)


def snapshot_software_ocs(activo):
    """Captura el software instalado de un activo desde OCS (best-effort).

    Busca el EquipoOCS vinculado al activo (activo_local). Si OCS no está
    configurado/alcanzable o el equipo no está vinculado, devuelve [].

    Returns:
        Lista de dicts {"name", "version", "publisher"} (puede ser []).
    """
    equipo = (
        activo.equipo_ocs.first()
        if hasattr(activo, "equipo_ocs") and activo.equipo_ocs.exists()
        else None
    )
    if not equipo or not equipo.id_ocs:
        return []

    try:
        client = build_client()
        if not client.is_configured():
            logger.warning("OCS no configurado; snapshot de software vacío.")
            return []
        return client.get_software(str(equipo.id_ocs))
    except OCSClientException as exc:
        logger.warning("No se pudo obtener software OCS para %s: %s", activo.serial, exc)
        return []
    except Exception as exc:
        logger.warning("Error snapshot OCS para %s: %s", activo.serial, exc)
        return []