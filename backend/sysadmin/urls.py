from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('core.urls')),
    path('accounts/', include('accounts.urls')),
    path('usuarios/', include('usuarios.urls', namespace='usuarios')),
    path('inventario/', include('inventario.urls', namespace='inventario')),
    path('reports/', include('reports.urls', namespace='reports')),
    path('mantenimiento/', include('mantenimiento.urls', namespace='mantenimiento')),
    path('passwords/', include('passwords.urls', namespace='passwords')),
    path('yule/', include('yule.urls', namespace='yule')),
    path('documentos/', include('documentos.urls', namespace='documentos')),
    path('administracion/', include('administracion.urls', namespace='administracion')),
    path('notificaciones/', include('notificaciones.urls', namespace='notificaciones')),
    path('soporte/', include('soporte.urls', namespace='soporte')),
    path('licencias/', include('licencias.urls', namespace='licencias')),
    path('prestamos/', include('prestamos.urls', namespace='prestamos')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
