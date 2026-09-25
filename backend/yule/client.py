import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests
from django.conf import settings
from django.utils import timezone

from .models import ConfiguracionYule

logger = logging.getLogger(__name__)


class OCSClientException(Exception):
    """Excepción base del cliente OCS"""
    pass


class OCSConnectionError(OCSClientException):
    """Error de conexión con OCS"""
    pass


class OCSAuthError(OCSClientException):
    """Error de autenticación con OCS"""
    pass


@dataclass
class OCSClient:
    base_url: str
    user: str
    token: str
    verify_ssl: bool = True
    timeout: int = 15
    max_retries: int = 3
    computers_limit: int = 1000

    def is_configured(self) -> bool:
        """Verifica si el cliente está configurado correctamente"""
        return bool(self.base_url and self.user and self.token)

    def _headers(self) -> Dict[str, str]:
        """Headers estándar para requests OCS"""
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "ocs-apirequest": "true",
        }

    def _build_url(self, path: str) -> str:
        """Construye URL completa para endpoint"""
        return f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"

    def request(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        method: str = "get",
        data: Optional[Dict[str, Any]] = None,
    ) -> requests.Response:
        """
        Realiza request a OCS con reintentos y manejo de errores.
        
        Args:
            path: Path del endpoint relativo a base_url
            params: Query parameters
            method: HTTP method (get, post, etc)
            data: Body data para POST/PUT
            
        Returns:
            requests.Response
            
        Raises:
            OCSConnectionError: Si no se puede conectar
            OCSAuthError: Si hay error de autenticación
            OCSClientException: Para otros errores
        """
        if not self.is_configured():
            raise OCSClientException("OCS client is not configured")

        url = self._build_url(path)
        last_exception = None

        for attempt in range(self.max_retries):
            try:
                if method.lower() == "get":
                    response = requests.get(
                        url,
                        params=params,
                        headers=self._headers(),
                        auth=(self.user, self.token),
                        timeout=self.timeout,
                        verify=self.verify_ssl,
                    )
                elif method.lower() == "post":
                    response = requests.post(
                        url,
                        json=data,
                        params=params,
                        headers=self._headers(),
                        auth=(self.user, self.token),
                        timeout=self.timeout,
                        verify=self.verify_ssl,
                    )
                else:
                    raise OCSClientException(f"Unsupported method: {method}")

                # Check para errores HTTP
                if response.status_code == 401:
                    raise OCSAuthError(f"Authentication failed: {response.status_code}")
                elif response.status_code == 403:
                    raise OCSAuthError(f"Access forbidden: {response.status_code}")
                elif response.status_code >= 500:
                    # Retry en errors 5xx
                    last_exception = OCSConnectionError(
                        f"Server error: {response.status_code}"
                    )
                    if attempt < self.max_retries - 1:
                        wait_time = 2 ** attempt  # exponential backoff
                        logger.warning(
                            f"OCS request failed (attempt {attempt + 1}/{self.max_retries}), "
                            f"retrying in {wait_time}s: {last_exception}"
                        )
                        import time
                        time.sleep(wait_time)
                        continue
                elif response.status_code >= 400:
                    raise OCSClientException(
                        f"Client error: {response.status_code} — {response.text}"
                    )

                return response

            except requests.Timeout as e:
                last_exception = OCSConnectionError(f"Request timeout: {str(e)}")
                if attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(
                        f"OCS timeout (attempt {attempt + 1}/{self.max_retries}), "
                        f"retrying in {wait_time}s"
                    )
                    import time
                    time.sleep(wait_time)
                    continue
            except requests.ConnectionError as e:
                last_exception = OCSConnectionError(f"Connection failed: {str(e)}")
                if attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(
                        f"OCS connection failed (attempt {attempt + 1}/{self.max_retries}), "
                        f"retrying in {wait_time}s"
                    )
                    import time
                    time.sleep(wait_time)
                    continue

        # Si llegamos aquí, agotamos reintentos
        raise last_exception or OCSConnectionError("Failed after max retries")

    def _json_body(self, response: requests.Response) -> Any:
        """Devuelve el JSON de la respuesta de OCS.

        OCS Inventory NG no siempre devuelve JSON válido: con `limit=0` (o sin
        `limit`) en `/computers` responde texto plano con un error de PHP, y sin
        filas devuelve `null` o cuerpo vacío. Sin esto, `response.json()` lanzaba
        `Expecting value: line 1 column 1` y el error real quedaba escondido.

        - cuerpo vacío o `null` → `None` (el llamador lo trata como lista vacía)
        - cuerpo no-JSON → OCSClientException con el texto real de OCS
        """
        body = (response.text or "").strip()
        if not body:
            return None
        try:
            return response.json()
        except ValueError as e:
            raise OCSClientException(
                f"OCS devolvió una respuesta que no es JSON "
                f"(HTTP {response.status_code}): {body[:200]}"
            ) from e

    @staticmethod
    def _computers_from_payload(data: Any) -> List[Dict[str, Any]]:
        """Normaliza a lista la respuesta de `/computers`.

        OCS 2.12 devuelve un **dict indexado por ID** (`{"1": {...}}`) cuando hay
        equipos, no una lista; otras versiones devuelven `{"computers": [...]}` o
        una lista directa. Sin normalizar, el sync contaba 0 equipos.
        """
        if data is None:
            return []
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            computers = data.get("computers")
            if isinstance(computers, list):
                return [item for item in computers if isinstance(item, dict)]
            # Dict indexado por ID: el valor es cada equipo.
            values = [value for value in data.values() if isinstance(value, dict)]
            if values:
                return values
        logger.warning(f"Unexpected OCS response format: {str(data)[:200]}")
        return []

    def get_computers(self) -> List[Dict[str, Any]]:
        """
        Obtiene lista de computadoras desde OCS.

        Returns:
            Lista de computadoras con sus datos

        Raises:
            OCSClientException: Si hay error en la sincronización
        """
        try:
            # OCS 2.12 rechaza limit=0: con ese valor /computers devuelve texto
            # plano ("Argument...") en vez de JSON. Hay que pedir un límite
            # positivo explícito.
            response = self.request("computers", params={"limit": self.computers_limit})
            response.raise_for_status()
            return self._computers_from_payload(self._json_body(response))

        except OCSClientException:
            raise
        except Exception as e:
            raise OCSClientException(f"Failed to parse OCS response: {str(e)}")

    def get_software(self, computer_id: str) -> List[Dict[str, Any]]:
        """Obtiene el software instalado de una computadora OCS (endpoint
        `computer/{id}` con su sección `software`).

        Returns:
            Lista normalizada de {"name", "version", "publisher"}.
            Vacía si el equipo no tiene software o el formato no es el esperado.

        Raises:
            OCSClientException: errores de conexión/autenticación.
        """
        try:
            response = self.request(f"computer/{computer_id}")
            response.raise_for_status()
            data = self._json_body(response)

            if isinstance(data, dict) and "software" in data:
                raw = data["software"]
            elif isinstance(data, list) and data and isinstance(data[0], dict) and "software" in data[0]:
                raw = data[0]["software"]
            elif isinstance(data, dict):
                # OCS 2.12 indexa por ID: {"1": {"software": [...]}}
                raw = []
                for value in data.values():
                    if isinstance(value, dict) and "software" in value:
                        raw = value["software"]
                        break
            else:
                raw = []

            software = []
            if isinstance(raw, list):
                for item in raw:
                    if not isinstance(item, dict):
                        continue
                    software.append({
                        "name": item.get("name") or item.get("NAME") or "",
                        "version": item.get("version") or item.get("VERSION") or "",
                        "publisher": item.get("publisher") or item.get("PUBLISHER") or "",
                    })
            return [s for s in software if s["name"]]

        except OCSClientException:
            raise
        except Exception as e:
            raise OCSClientException(f"Failed to parse software OCS: {str(e)}")

    def test_connection(self) -> bool:
        """Verifica la conexión con OCS"""
        try:
            response = self.request("computers", params={"limit": 1})
            return response.status_code == 200
        except OCSClientException as e:
            logger.error(f"OCS connection test failed: {e}")
            return False


def build_client() -> OCSClient:
    """Factory para crear cliente OCS.

    Prioridad:
      1. Configuración de la BD (ConfiguracionYule activa). Si la banda
         `integracion_activa` está desactivada, devuelve un cliente sin
         configurar (is_configured() = False) → el sync no corre y las vistas
         degradan a [].
      2. Fallback a settings/env (OCS_BASE_URL, OCS_USER, OCS_TOKEN) cuando no
         hay fila en BD, para no romper el despliegue actual.
    """
    config = ConfiguracionYule.objects.filter(activa=True).order_by("id").first()

    if config is not None:
        if not config.integracion_activa:
            return OCSClient(base_url="", user="", token="", verify_ssl=settings.OCS_VERIFY_SSL)
        if config.url and config.usuario:
            return OCSClient(
                base_url=config.url,
                user=config.usuario,
                token=config.get_ocs_password(),
                verify_ssl=settings.OCS_VERIFY_SSL,
            )

    return OCSClient(
        base_url=settings.OCS_BASE_URL,
        user=settings.OCS_USER,
        token=settings.OCS_TOKEN,
        verify_ssl=settings.OCS_VERIFY_SSL,
    )
