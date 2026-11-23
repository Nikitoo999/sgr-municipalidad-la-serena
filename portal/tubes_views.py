"""Tubos de trabajo: delegación, Antena y Cartas, con estados y código de verificación (3.6).

Unidad 3 (formato Card / modelo Canvas): la vista por defecto es un tablero de
cuatro columnas (Ingresados, Pendientes, En proceso, Realizados) con cuatro
indicadores arriba; la planilla (tabla paginada) sigue disponible.
"""
from collections import Counter
from urllib.parse import urlencode

from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import TemplateView

from operaciones import rules
from operaciones.models import Employee, TubeEntry
from sgr_core.models import Delegation

from . import access
from .access import ModulePermissionMixin
from .audit import audit
from .modules import MODULE_ICONS, MODULE_LABELS

POR_PAGINA = 25
#: Tarjetas por columna en el tablero (el resto se consulta en la planilla).
POR_COLUMNA = 60
#: "Realizado" solo se alcanza cerrando con foto y código de verificación.
ESTADOS_EDITABLES = [
    (valor, etiqueta) for valor, etiqueta in TubeEntry.Status.choices
    if valor != TubeEntry.Status.DONE
]
#: Columnas del tablero, en orden: (estado, título, clase de color).
COLUMNAS_TABLERO = (
    (TubeEntry.Status.RECEIVED, "1. Ingresados", "col-received"),
    (TubeEntry.Status.PENDING, "2. Pendientes", "col-pending"),
    (TubeEntry.Status.IN_PROGRESS, "3. En proceso", "col-progress"),
    (TubeEntry.Status.DONE, "4. Realizados", "col-done"),
)
#: Siguiente paso sugerido en cada tarjeta (botón rápido).
SIGUIENTE_ESTADO = {
    TubeEntry.Status.RECEIVED: (TubeEntry.Status.PENDING, "A Pendiente"),
    TubeEntry.Status.PENDING: (TubeEntry.Status.IN_PROGRESS, "A Proceso"),
    TubeEntry.Status.IN_PROGRESS: (TubeEntry.Status.DONE, "Realizar"),
}
VISTAS = ("tablero", "planilla")


def tubos_del_alcance(request):
    """Solicitudes visibles según rol y delegación activa."""
    role = access.get_role(request.user)
    active = access.get_active_delegation(request)
    qs = TubeEntry.objects.filter(deleted_at__isnull=True)
    if role is None or active is None:
        return qs.none()
    if active != access.ALL_DELEGATIONS:
        qs = qs.filter(delegation_id=active.pk)
    if role.scope == "own_records":
        qs = qs.filter(responsible__user_id=request.user.pk)
    return qs


def _pct(parte, total):
    return round(parte * 100 / total, 1) if total else None


def indicadores(conteo):
    """Las cuatro tarjetas de resumen del tablero."""
    validos = sum(n for st, n in conteo.items() if st != TubeEntry.Status.NOT_APPLICABLE)
    realizados = conteo.get(TubeEntry.Status.DONE, 0)
    tasa = _pct(realizados, validos)
    return [
        {"clave": "total", "titulo": "Gestiones en tubo", "valor": validos,
         "detalle": "Derivadas para seguimiento", "css": "k-total"},
        {"clave": "done", "titulo": "Realizadas / concluidas", "valor": realizados,
         "detalle": f"Tasa de resolución: {str(tasa).replace('.', ',')} %" if tasa is not None
         else "Tasa de resolución: —", "css": "k-done"},
        {"clave": "in_progress", "titulo": "En proceso activo", "valor": conteo.get(TubeEntry.Status.IN_PROGRESS, 0),
         "detalle": "Con cuadrilla o área de apoyo", "css": "k-progress"},
        {"clave": "pending", "titulo": "Pendientes / alerta", "valor": conteo.get(TubeEntry.Status.PENDING, 0),
         "detalle": "Esperando gestión técnica", "css": "k-alert"},
    ]


class TubeListView(LoginRequiredMixin, ModulePermissionMixin, TemplateView):
    template_name = "portal/tubes.html"
    module = "achievements"
    action = "view"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        info = access.get_access(self.request)
        canal = self.request.GET.get("canal", "")
        estado = self.request.GET.get("estado", "")
        vista = self.request.GET.get("vista", "")
        if vista not in VISTAS:
            vista = VISTAS[0]

        base = tubos_del_alcance(self.request)
        if canal in TubeEntry.Channel.values:
            base = base.filter(channel=canal)
        else:
            canal = ""

        conteo = Counter(base.values_list("status", flat=True))
        validos = sum(n for st, n in conteo.items() if st != TubeEntry.Status.NOT_APPLICABLE)
        realizados = conteo.get(TubeEntry.Status.DONE, 0)
        porcentaje = _pct(realizados, validos)
        resumen = [(etiqueta, conteo.get(valor, 0)) for valor, etiqueta in TubeEntry.Status.choices]

        qs = base
        if estado in TubeEntry.Status.values:
            qs = qs.filter(status=estado)
        else:
            estado = ""
        qs = qs.select_related("delegation", "responsible__user")

        hoy = timezone.localdate()
        columnas, pagina = [], None
        if vista == "tablero":
            for valor, titulo, css in COLUMNAS_TABLERO:
                if estado and estado != valor:
                    continue
                orden = ("-completed_at", "-pk") if valor == TubeEntry.Status.DONE else ("due_date", "request_date", "pk")
                tarjetas = list(qs.filter(status=valor).order_by(*orden)[:POR_COLUMNA])
                for tarjeta in tarjetas:
                    tarjeta.siguiente = SIGUIENTE_ESTADO.get(tarjeta.status)
                    tarjeta.vencida = bool(
                        tarjeta.due_date and tarjeta.due_date < hoy and valor != TubeEntry.Status.DONE
                    )
                columnas.append({
                    "estado": valor, "titulo": titulo, "css": css,
                    "tarjetas": tarjetas, "total": conteo.get(valor, 0),
                })
        else:
            pagina = Paginator(qs, POR_PAGINA).get_page(self.request.GET.get("page"))

        active = access.get_active_delegation(self.request)
        delegaciones, responsables = [], []
        if info.can("achievements", "create"):
            delegaciones = access.allowed_delegations(self.request.user)
            responsables = Employee.objects.filter(
                deleted_at__isnull=True, user__is_active=True,
                delegation_id__in=[d.pk for d in delegaciones],
            ).select_related("user", "delegation").order_by("delegation__name", "user__first_name")

        filtros = {k: v for k, v in (("canal", canal), ("estado", estado)) if v}
        context.update({
            "active_module": "achievements",
            "module_label": MODULE_LABELS["achievements"],
            "module_icon": MODULE_ICONS["achievements"],
            "vista": vista,
            "columnas": columnas,
            "indicadores": indicadores(conteo),
            "no_aplica": conteo.get(TubeEntry.Status.NOT_APPLICABLE, 0),
            "pagina": pagina,
            "canal": canal,
            "estado": estado,
            "canales": TubeEntry.Channel.choices,
            "estados": TubeEntry.Status.choices,
            "estados_editables": ESTADOS_EDITABLES,
            "resumen": resumen,
            "porcentaje": porcentaje,
            "querystring": urlencode({**filtros, "vista": vista}),
            "url_tablero": "?" + urlencode({**filtros, "vista": "tablero"}),
            "url_planilla": "?" + urlencode({**filtros, "vista": "planilla"}),
            "volver": self.request.get_full_path(),
            "can_create": info.can("achievements", "create"),
            "can_edit": info.can("achievements", "edit"),
            "delegaciones": delegaciones,
            "responsables": responsables,
            "activa_pk": active.pk if active not in (None, access.ALL_DELEGATIONS) else None,
            "hoy": hoy.isoformat(),
        })
        return context


class TubeEntryForm(forms.ModelForm):
    class Meta:
        model = TubeEntry
        fields = [
            "delegation", "channel", "title", "origin", "requester", "territory", "responsible",
            "request_date", "due_date", "support_area", "notes", "letter_number", "contact_phone",
        ]

    def __init__(self, *args, delegations=(), **kwargs):
        super().__init__(*args, **kwargs)
        pks = [d.pk for d in delegations]
        self.fields["delegation"].queryset = Delegation.objects.filter(pk__in=pks)
        self.fields["responsible"].queryset = Employee.objects.filter(
            deleted_at__isnull=True, user__is_active=True, delegation_id__in=pks,
        )

    def clean_request_date(self):
        """Nuevo requerimiento, punto 4: la semana se completa hasta el lunes siguiente."""
        fecha = self.cleaned_data.get("request_date")
        error = rules.past_week_entry_error(fecha)
        if error:
            raise forms.ValidationError(error)
        if fecha and fecha > timezone.localdate():
            raise forms.ValidationError("La fecha de solicitud no puede ser futura.")
        return fecha

    def clean(self):
        cleaned = super().clean()
        delegacion, responsable = cleaned.get("delegation"), cleaned.get("responsible")
        if delegacion and responsable and responsable.delegation_id != delegacion.pk:
            self.add_error("responsible", "El responsable debe pertenecer a la delegación elegida.")
        return cleaned


class TubeCloseForm(forms.ModelForm):
    code = forms.CharField(max_length=8)

    class Meta:
        model = TubeEntry
        fields = ["proof_image"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["proof_image"].required = True

    def clean_code(self):
        ingresado = self.cleaned_data["code"].strip().upper()
        if ingresado != self.instance.verification_code:
            raise forms.ValidationError("El código no coincide con el de la solicitud.")
        return ingresado


def _errores(form):
    return "; ".join(e for lista in form.errors.values() for e in lista)


def _volver(request):
    """Vuelve al tablero o planilla de origen (con sus filtros) si es seguro."""
    destino = request.POST.get("next", "")
    if destino and url_has_allowed_host_and_scheme(
        destino, allowed_hosts={request.get_host()}, require_https=request.is_secure(),
    ) and destino.startswith(reverse("tubes")):
        return redirect(destino)
    return redirect("tubes")


def _es_ajax(request):
    return request.headers.get("x-requested-with") == "XMLHttpRequest"


class TubeCreateView(LoginRequiredMixin, ModulePermissionMixin, View):
    """Ingresa una solicitud al tubo."""

    module = "achievements"
    action = "create"

    def post(self, request):
        form = TubeEntryForm(request.POST, delegations=access.allowed_delegations(request.user))
        if form.is_valid():
            entrada = form.save()
            audit(request, "create", module="achievements",
                object_repr=f"Tubo {entrada.code}", detail=f"Ingresada por {request.user}")
            aviso = "" if entrada.has_contact else (
                " Sin teléfono del solicitante la solicitud no suma puntaje: agrégalo apenas lo tengas."
            )
            messages.success(
                request,
                f"Solicitud {entrada.code} ingresada. Código de verificación: {entrada.verification_code}.{aviso}",
            )
        else:
            messages.error(request, f"No se pudo ingresar la solicitud: {_errores(form)}")
        return _volver(request)


class TubeStatusView(LoginRequiredMixin, ModulePermissionMixin, View):
    """Cambia el estatus de una solicitud (sin llegar a Realizado).

    Desde el tablero (arrastrar y soltar) responde JSON; desde un formulario
    redirige de vuelta con un mensaje.
    """

    module = "achievements"
    action = "edit"

    def post(self, request, entry_id):
        entrada = get_object_or_404(tubos_del_alcance(request), pk=entry_id)
        nuevo = request.POST.get("status", "")
        ok, texto = False, ""
        if entrada.status == TubeEntry.Status.DONE:
            texto = f"{entrada.code} ya está realizada."
        elif nuevo not in dict(ESTADOS_EDITABLES):
            texto = "Estatus no válido. Para marcar como Realizado hay que cerrar con foto y código."
        else:
            ok = True
            if entrada.status != nuevo:
                entrada.status = nuevo
                entrada.save(update_fields=["status", "updated_at"])
                audit(request, "edit", module="achievements",
                    object_repr=f"Tubo {entrada.code}", detail=f"Estatus: {entrada.get_status_display()}")
            texto = f"{entrada.code}: estatus actualizado a {entrada.get_status_display()}."
        if _es_ajax(request):
            return JsonResponse(
                {"ok": ok, "message": texto, "status": entrada.status,
                 "label": entrada.get_status_display()},
                status=200 if ok else 400,
            )
        if ok:
            messages.success(request, texto)
        elif entrada.status == TubeEntry.Status.DONE:
            messages.info(request, texto)
        else:
            messages.error(request, texto)
        return _volver(request)


class TubeCloseView(LoginRequiredMixin, ModulePermissionMixin, View):
    """Cierra una solicitud como Realizada con foto de respaldo y código de verificación."""

    module = "achievements"
    action = "edit"

    def post(self, request, entry_id):
        entrada = get_object_or_404(tubos_del_alcance(request), pk=entry_id)
        if entrada.status == TubeEntry.Status.DONE:
            messages.info(request, f"{entrada.code} ya está realizada.")
            return _volver(request)
        form = TubeCloseForm(request.POST, request.FILES, instance=entrada)
        if form.is_valid():
            entrada = form.save(commit=False)
            entrada.status = TubeEntry.Status.DONE
            entrada.completed_at = timezone.now()
            entrada.save()
            audit(request, "edit", module="achievements",
                object_repr=f"Tubo {entrada.code}", detail=f"Cerrada con foto por {request.user}")
            messages.success(request, f"{entrada.code} cerrada como realizada.")
        else:
            messages.error(request, f"No se pudo cerrar {entrada.code}: {_errores(form)}")
        return _volver(request)
