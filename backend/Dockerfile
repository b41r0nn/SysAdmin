FROM python:3.11-slim

# Librerías de sistema que necesita WeasyPrint en tiempo de ejecución. Todas las
# dependencias de Python se instalan desde wheels, así que no hace falta
# build-essential ni cabeceras -dev en la imagen final.
RUN apt-get update && apt-get install -y \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libharfbuzz-subset0 \
    libjpeg62-turbo \
    libopenjp2-7 \
    && rm -rf /var/lib/apt/lists/*

# Usuario sin privilegios. UID 1000 = usuario "sistemas" del servidor, dueño
# del bind mount de media/ en el host.
RUN useradd --uid 1000 --create-home --shell /usr/sbin/nologin app

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --only-binary=:all: -r requirements.txt

# El código va dentro de la imagen (no se monta desde el host): cada despliegue
# reconstruye la imagen.
COPY --chown=app:app . /app
RUN mkdir -p /app/staticfiles /app/media && chown app:app /app/staticfiles /app/media

USER app

EXPOSE 8000

# Se invoca con bash explícito para no depender del bit de ejecución ni de los
# finales de línea con que llegue el archivo.
ENTRYPOINT ["bash", "/app/entrypoint.sh"]
