from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "SGR Municipalidad de La Serena"
admin.site.site_title = "Portal de Administración SGR"
admin.site.index_title = "Gestión de Resultados y Control Territorial"

handler403 = "portal.error_views.error_403"
handler404 = "portal.error_views.error_404"
handler500 = "portal.error_views.error_500"

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('portal.urls')),
]
