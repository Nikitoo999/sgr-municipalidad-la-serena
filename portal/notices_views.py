"""Avisos (traspasos de trimestre) y alertas operativas del usuario."""

import re

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.views import View
from django.views.generic import TemplateView

from operaciones.models import AlertReview

from . import access
from .alerts import alertas_baratas, alertas_de_gestion, notices_for, reviewed_keys

_KEY = re.compile(r"^[a-z0-9:-]{3,120}$")
_NIVEL_ORDEN = {"alta": 0, "media": 1, "info": 2}


class NoticesView(LoginRequiredMixin, TemplateView):
    template_name = "portal/notices.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and access.get_role(request.user) is None:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        avisos = list(notices_for(self.request).prefetch_related("read_by")[:50])
        leidos = set(
            notices_for(self.request).filter(read_by=user).values_list("pk", flat=True)
        )
        for aviso in avisos:
            aviso.leido = aviso.pk in leidos
        alertas = alertas_baratas(self.request) + alertas_de_gestion(self.request)
        revisadas = reviewed_keys(user, [a.key for a in alertas])
        alertas.sort(key=lambda a: (_NIVEL_ORDEN.get(a.nivel, 3), a.fecha))
        context.update({
            "active_module": "notices",
            "avisos": avisos,
            "no_leidos": sum(1 for a in avisos if not a.leido),
            "pendientes": [a for a in alertas if a.key not in revisadas],
            "revisadas": [a for a in alertas if a.key in revisadas],
        })
        return context


class NoticesMarkReadView(LoginRequiredMixin, View):
    """Marca como leídos todos los avisos visibles (solo POST)."""

    def post(self, request):
        avisos = list(notices_for(request).exclude(read_by=request.user))
        for aviso in avisos:
            aviso.read_by.add(request.user)
        messages.success(request, f"{len(avisos)} aviso(s) marcado(s) como leídos." if avisos else "No había avisos sin leer.")
        return redirect("notices")


class AlertReviewView(LoginRequiredMixin, View):
    """Marca una alerta como revisada sin borrar el evento original (solo POST)."""

    def post(self, request):
        key = (request.POST.get("key") or "").strip()
        if not _KEY.match(key):
            messages.error(request, "Alerta no válida.")
        else:
            AlertReview.objects.get_or_create(user=request.user, key=key)
            messages.success(request, "Alerta marcada como revisada.")
        return redirect("notices")
