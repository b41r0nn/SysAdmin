from django.db import migrations

# Contenido inicial de los checklists (§B2 del diseño de mantenimiento v2) como
# (sección, descripción, ¿aplica en garantía?). Las listas van aquí y no se
# importan de la app: una migración tiene que dar siempre el mismo resultado,
# aunque después cambien los modelos o las constantes.
PORTATIL = [
    ("Hardware", "Desarme del equipo", False),
    ("Hardware", "Pantalla", False),
    ("Hardware", "Bisagras", False),
    ("Hardware", "Batería", False),
    ("Limpieza", "Limpieza externa", True),
    ("Limpieza", "Limpieza interna", False),
    ("Limpieza", "Limpieza de puertos", False),
    ("Mantenimiento lógico", "Actualizaciones de Windows", True),
    ("Mantenimiento lógico", "Antivirus", True),
    ("Mantenimiento lógico", "Archivos temporales", True),
    ("Mantenimiento lógico", "Estado del disco", True),
    ("Mantenimiento lógico", "Programas de inicio", True),
]
ESCRITORIO = [
    ("Hardware", "Desarme del equipo", False),
    ("Limpieza", "Limpieza externa", True),
    ("Limpieza", "Limpieza interna", False),
    ("Limpieza", "Limpieza de puertos", False),
    ("Mantenimiento lógico", "Actualizaciones de Windows", True),
    ("Mantenimiento lógico", "Antivirus", True),
    ("Mantenimiento lógico", "Archivos temporales", True),
    ("Mantenimiento lógico", "Estado del disco", True),
    ("Mantenimiento lógico", "Programas de inicio", True),
]
# La frecuencia de ambas es la de por defecto del modelo (12 meses).
PLANTILLAS = {"portatil": PORTATIL, "escritorio": ESCRITORIO}


def crear_plantillas_iniciales(apps, schema_editor):
    Plantilla = apps.get_model("mantenimiento", "PlantillaChecklist")
    Punto = apps.get_model("mantenimiento", "PuntoPlantilla")
    for tipo, puntos in PLANTILLAS.items():
        plantilla, creada = Plantilla.objects.get_or_create(tipo_dispositivo=tipo)
        if not creada:
            continue  # ya existe: no se pisa lo que alguien haya configurado
        # La posición es el índice dentro de la lista de cada plantilla, desde 0.
        Punto.objects.bulk_create(
            Punto(
                plantilla=plantilla,
                seccion=seccion,
                descripcion=descripcion,
                posicion=posicion,
                aplica_en_garantia=aplica_en_garantia,
            )
            for posicion, (seccion, descripcion, aplica_en_garantia) in enumerate(puntos)
        )


def quitar_plantillas_iniciales(apps, schema_editor):
    Plantilla = apps.get_model("mantenimiento", "PlantillaChecklist")
    # Los puntos se van en cascada.
    Plantilla.objects.filter(tipo_dispositivo__in=list(PLANTILLAS)).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("mantenimiento", "0009_plantillachecklist_puntoplantilla"),
    ]

    operations = [
        migrations.RunPython(crear_plantillas_iniciales, quitar_plantillas_iniciales),
    ]
