"""Consulta de auditoría (HU-30): quién cambió qué dato y cuándo.

Solo lectura y solo para el alcance "Todas las delegaciones"
(superadministrador). No existe ninguna vista que modifique o borre eventos.
"""

import json
from datetime import datetime, time, timedelta

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone
from django.utils.http import urlencode
from django.views.generic import TemplateView

from . import access
from .models import AuditLog

POR_PAGINA = 50


def _fecha(valor):
    try:
        return datetime.strptime(valor, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


class AuditLogView(LoginRequiredMixin, TemplateView):
    template_name = "portal/audit_log.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            role = access.get_role(request.user)
            if role is None or role.scope != "all":
                raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        g = self.request.GET
        qs = AuditLog.objects.select_related("user").order_by("-created_at", "-pk")
        modulo, accion, usuario = g.get("modulo", ""), g.get("accion", ""), g.get("usuario", "").strip()
        desde, hasta = _fecha(g.get("desde")), _fecha(g.get("hasta"))
        if modulo:
            qs = qs.filter(module=modulo)
        if accion:
            qs = qs.filter(action=accion)
        if usuario:
            qs = qs.filter(Q(user__username__icontains=usuario) | Q(user__email__icontains=usuario)
                           | Q(user__first_name__icontains=usuario) | Q(user__last_name__icontains=usuario))
        if desde:
            qs = qs.filter(created_at__gte=timezone.make_aware(datetime.combine(desde, time.min)))
        if hasta:
            qs = qs.filter(created_at__lt=timezone.make_aware(datetime.combine(hasta + timedelta(days=1), time.min)))
        pagina = Paginator(qs, POR_PAGINA).get_page(g.get("page"))
        for evento in pagina:
            try:
                evento.cambios = json.loads(evento.changes) if evento.changes else []
            except ValueError:
                evento.cambios = []
        filtros = {k: v for k, v in (("modulo", modulo), ("accion", accion), ("usuario", usuario),
                                     ("desde", g.get("desde", "")), ("hasta", g.get("hasta", ""))) if v}
        context.update({
            "active_module": "audit",
            "pagina": pagina,
            "modulos": AuditLog.objects.exclude(module="").values_list("module", flat=True).distinct().order_by("module"),
            "acciones": AuditLog.objects.values_list("action", flat=True).distinct().order_by("action"),
            "filtros": filtros,
            "querystring": urlencode(filtros),
        })
        return context
