"""Ventana emergente (modal) para los formularios de "Nuevo ...".

El listado abre el formulario de creación dentro de un ``<iframe>`` en una
ventana compacta (``portal/static/portal/js/modal.js``). La página del
formulario es la misma de siempre, con ``?modal=1``:

- ``base.html`` oculta la cabecera, el menú y el pie (modo "embed").
- Si el envío es válido, la vista responde con una redirección; aquí se
  reemplaza por una página mínima que avisa a la ventana principal para que
  cierre el modal y recargue (el mensaje de éxito queda en la sesión y se
  muestra con SweetAlert2 al recargar).
- Solo estas respuestas permiten ser enmarcadas, y únicamente por el mismo
  origen (``X-Frame-Options: SAMEORIGIN``); el resto del sitio sigue en DENY.

Sin JavaScript el botón "Nuevo ..." sigue llevando a la página completa.
"""

from django.http import HttpResponse, HttpResponseRedirect
from django.template.loader import render_to_string
from django.utils.http import url_has_allowed_host_and_scheme

MODAL_PARAM = "modal"


def is_modal(request):
    """¿La petición viene desde la ventana emergente?"""
    return request.GET.get(MODAL_PARAM) == "1"


def finalize_modal_response(request, response):
    """Adapta la respuesta de una vista de formulario abierta en el modal."""
    if not is_modal(request):
        return response
    if request.method == "POST" and isinstance(response, HttpResponseRedirect):
        target = response.url
        if not url_has_allowed_host_and_scheme(
            target, allowed_hosts={request.get_host()}, require_https=request.is_secure(),
        ):
            target = "/"
        # Sin ``request``: así no corren los procesadores de contexto, que
        # consumirían el mensaje de éxito antes de que el listado se recargue.
        response = HttpResponse(
            render_to_string("portal/modal_done.html", {"redirect_url": target}),
        )
    response["X-Frame-Options"] = "SAMEORIGIN"
    return response


class ModalFormMixin:
    """Mixin para vistas de creación que pueden abrirse en el modal."""

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        return finalize_modal_response(request, response)
