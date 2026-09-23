# Etiquetas QR de Activos · Impresión y Tamaño

> Fecha: 2026-09-23 — Tamaño confirmado leyendo la plantilla fuente (no asumir valores antiguos de README/handoffs).

## Tamaño exacto de la plaqueta

| Elemento       | Medida                         | Definición en la plantilla |
| -------------- | ------------------------------ | --------------------------- |
| **Plaqueta**   | **50 mm × 30 mm**              | `.label { width: 50mm; height: 30mm }` |
| Radio de esquina | 2 mm                          | `.label { border-radius: 2mm }` |
| **QR interno** | 14 mm × 14 mm                  | `.qr { width: 14mm; height: 14mm }` |
| **Papel (hoja)** | **A4 vertical**, margen 10 mm | `@page { size: A4 portrait; margin: 10mm }` |

La plaqueta se imprime **varias por hoja A4** (selección masiva de hasta 8 por página); el `@page` solo define la hoja de papel. El tamaño de la plaqueta física está en `.label`.

## Impresión en proveedor externo

Si se manda a imprimir en un proveedor externo (stickers o plaquetas adhesivas), **pedir el tamaño exacto 50 × 30 mm** (no aproximado). Un tamaño distinto degrada la legibilidad del QR (14×14 mm) y desalinea el recuadro del sticker.

## Archivo fuente

La plantilla se regenera desde:

```
backend/inventario/templates/inventario/etiqueta_pdf.html
```

Se renderiza con WeasyPrint (standalone, patrón `acta_pdf.html`). Si en el futuro cambia el tamaño de la plaqueta, ese archivo es el único lugar donde ajustar `width`/`height` de `.label` (y `.qr` si hace falta).

Vistas que generan el PDF (en `backend/inventario/views.py`):
- `inventario/views.py` → `qr_etiqueta_pdf` (etiqueta individual) y `qr_etiquetas_masivas` (selección masiva).
- Rutas: `inventario/urls.py` → `etiqueta` y `etiquetas`.