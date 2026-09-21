from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render

from accounts.permisos import requiere_permiso

from .forms import CategoriaForm, DocumentoForm, FiltroDocumentoForm
from .models import Categoria, Documento, TIPOS_DOCUMENTO


@requiere_permiso("documentos", "lectura")
def lista_documentos(request):
    qs = Documento.objects.select_related("categoria", "creado_por").all()

    form_filtro = FiltroDocumentoForm(request.GET or None)
    q = request.GET.get("q", "").strip()
    tipo = request.GET.get("tipo_documento", "").strip()
    categoria_id = request.GET.get("categoria", "").strip()

    if q:
        qs = qs.filter(
            Q(titulo__icontains=q)
            | Q(descripcion__icontains=q)
            | Q(version__icontains=q)
        )
    if tipo:
        qs = qs.filter(tipo_documento=tipo)
    if categoria_id:
        qs = qs.filter(categoria_id=categoria_id)

    ctx = {
        "documentos": qs,
        "form_filtro": form_filtro,
        "tipos": TIPOS_DOCUMENTO,
        "categorias": Categoria.objects.all(),
        "filtro_q": q,
        "filtro_tipo": tipo,
        "filtro_categoria": categoria_id,
    }
    return render(request, "documentos/lista.html", ctx)


@requiere_permiso("documentos", "escritura")
def crear_documento(request):
    if request.method == "POST":
        form = DocumentoForm(request.POST, request.FILES)
        if form.is_valid():
            documento = form.save(commit=False)
            documento.creado_por = request.user
            documento.save()
            messages.success(request, f"Documento «{documento.titulo}» subido correctamente.")
            return redirect("documentos:lista")
        else:
            messages.error(request, "Corrige los errores del formulario.")
    else:
        form = DocumentoForm()

    return render(request, "documentos/form.html", {"form": form, "titulo": "Nuevo Documento"})


@requiere_permiso("documentos", "escritura")
def editar_documento(request, pk):
    documento = get_object_or_404(Documento, pk=pk)
    if request.method == "POST":
        form = DocumentoForm(request.POST, request.FILES, instance=documento)
        if form.is_valid():
            form.save()
            messages.success(request, f"Documento «{documento.titulo}» actualizado.")
            return redirect("documentos:lista")
        else:
            messages.error(request, "Corrige los errores del formulario.")
    else:
        form = DocumentoForm(instance=documento)

    return render(request, "documentos/form.html", {
        "form": form,
        "titulo": "Editar Documento",
        "documento": documento,
    })


@requiere_permiso("documentos", "escritura")
def eliminar_documento(request, pk):
    documento = get_object_or_404(Documento, pk=pk)
    if request.method == "POST":
        titulo = documento.titulo
        documento.delete()
        messages.success(request, f"Documento «{titulo}» eliminado.")
        return redirect("documentos:lista")
    return render(request, "documentos/confirmar_eliminar.html", {"documento": documento})


@requiere_permiso("documentos", "lectura")
def ver_documento(request, pk):
    documento = get_object_or_404(Documento, pk=pk, activo=True)
    if not documento.archivo:
        raise Http404("El documento no tiene archivo adjunto.")
    try:
        nombre = documento.archivo.name.split("/")[-1]
        return FileResponse(documento.archivo.open(), as_attachment=False, filename=nombre)
    except FileNotFoundError:
        raise Http404("Archivo no encontrado en el servidor.")


@requiere_permiso("documentos", "lectura")
def descargar_documento(request, pk):
    documento = get_object_or_404(Documento, pk=pk, activo=True)
    if not documento.archivo:
        raise Http404("El documento no tiene archivo adjunto.")
    try:
        return FileResponse(documento.archivo.open(), as_attachment=True, filename=documento.archivo.name.split("/")[-1])
    except FileNotFoundError:
        raise Http404("Archivo no encontrado en el servidor.")


# ── Categorías ────────────────────────────────────────────────────────────────

@requiere_permiso("documentos", "lectura")
def lista_categorias(request):
    ctx = {"categorias": Categoria.objects.all()}
    return render(request, "documentos/categorias_lista.html", ctx)


@requiere_permiso("documentos", "escritura")
def crear_categoria(request):
    if request.method == "POST":
        form = CategoriaForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Categoría creada correctamente.")
            return redirect("documentos:categorias_lista")
    else:
        form = CategoriaForm()
    return render(request, "documentos/form_categoria.html", {"form": form, "titulo": "Nueva Categoría"})


@requiere_permiso("documentos", "escritura")
def editar_categoria(request, pk):
    categoria = get_object_or_404(Categoria, pk=pk)
    if request.method == "POST":
        form = CategoriaForm(request.POST, instance=categoria)
        if form.is_valid():
            form.save()
            messages.success(request, "Categoría actualizada.")
            return redirect("documentos:categorias_lista")
    else:
        form = CategoriaForm(instance=categoria)
    return render(request, "documentos/form_categoria.html", {
        "form": form,
        "titulo": "Editar Categoría",
        "categoria": categoria,
    })


@requiere_permiso("documentos", "escritura")
def eliminar_categoria(request, pk):
    categoria = get_object_or_404(Categoria, pk=pk)
    if request.method == "POST":
        if categoria.documentos.exists():
            messages.error(request, "No se puede eliminar la categoría porque tiene documentos asociados.")
            return redirect("documentos:categorias_lista")
        nombre = categoria.nombre
        categoria.delete()
        messages.success(request, f"Categoría «{nombre}» eliminada.")
        return redirect("documentos:categorias_lista")
    return render(request, "documentos/confirmar_eliminar_categoria.html", {"categoria": categoria})
