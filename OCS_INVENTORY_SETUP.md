# Instalación de OCS Inventory NG y conexión con Yule

## Qué es y cómo se relaciona con SysAdmin

OCS Inventory NG es software externo, independiente de SysAdmin. Escanea
la red y guarda su propio inventario en su propia base de datos. El
módulo Yule de SysAdmin NO habla con los equipos directamente — solo
consulta la API REST de OCS bajo demanda, cuando se aprieta
"Sincronizar ahora".

Dos relaciones distintas:

- **Agente instalado en cada equipo → Servidor OCS**: automática,
  constante, reporta sola cada cierto tiempo.
- **Servidor OCS → SysAdmin/Yule**: manual, bajo demanda, solo al
  sincronizar. Trae la lista de equipos y los compara por serial/MAC
  contra los `Activo` ya cargados en el inventario.
- **Coincide por serial/MAC** → aparece como candidato de vinculación,
  pero el enlace no se hace solo. Hay que entrar al admin de Django
  (`/admin/yule/equiposocs/`) y setear manualmente el campo
  `activo_local` en el registro correspondiente.
- **No coincide con nada** → queda "sin match", mismo criterio.

## Instalación (servidor 192.168.1.250)

1. Descargar la plantilla oficial:

   ```bash
   mkdir -p ~/ocs && cd ~/ocs
   git clone https://github.com/OCSInventory-NG/OCSInventory-Docker-Image.git
   cd OCSInventory-Docker-Image/2.12.1
   ```

2. Editar `docker-compose.yml`: contraseñas de MySQL, puerto mapeado a
   8080 (`LISTEN_PORT: 80` / `ports: - "8080:80"`), `TZ: America/Bogota`.

3. Levantar:

   ```bash
   docker compose up -d
   docker compose ps
   ```

4. Si hay firewall: `sudo ufw allow 8080/tcp`

5. Completar el asistente inicial en `http://192.168.1.250:8080/ocsreports`.

6. Generar credenciales de la API REST:

   ```bash
   sudo apt install -y apache2-utils
   htpasswd -c nginx/auth/ocsapi.htpasswd sysadmin_api
   docker compose restart nginx
   ```

7. En SysAdmin, `/yule/` → Configuración OCS:

   - URL Base: `http://192.168.1.250:8080`
   - Usuario / Token: el usuario/contraseña del paso 6
   - Verificar SSL: No (certificado dummy por defecto)

8. Instalar el agente (`http://192.168.1.250:8080/download`) en un
   equipo de prueba y confirmar que "Sincronizar ahora" trae datos reales.

## Troubleshooting

- Sincronización falla / "Fallo" en el historial → confirmar que la
  URL Base sea alcanzable desde el contenedor de Django (no
  `localhost`), y que usuario/token coincidan con el htpasswd real.
- Si el `docker-compose.yml` de la versión usada no trae exactamente
  estas variables, revisar la documentación oficial:
  http://wiki.ocsinventory-ng.org/13.Docker-documentation/Using-the-docker-image/