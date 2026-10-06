from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "SGR Municipalidad de La Serena"
admin.site.site_title = "Portal de Administración SGR"
admin.site.index_title = "Gestión de Resultados y Control Territorial"

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('portal.urls')),
]
