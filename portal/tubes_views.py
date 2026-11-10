"""Tubos de trabajo: delegación, Antena y Cartas, con estados y código de verificación (3.6)."""
from collections import Counter
from urllib.parse import urlencode

from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from operaciones.models import Employee, TubeEntry
from sgr_core.models import Delegation

from . import access
from .access import ModulePermissionMixin
from .audit import audit
from .modules import MODULE_ICONS, MODULE_LABELS

POR_PAGINA = 25
#: "Realizado" solo se alcanza cerrando con foto y código de verificación.
ESTADOS_EDITABLES = [
    (valor, etiqueta) for valor, etiqueta in TubeEntry.Status.choices
    if valor != TubeEntry.Status.DONE
]


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


class TubeListView(LoginRequiredMixin, ModulePermissionMixin, TemplateView):
    template_name = "portal/tubes.html"
    module = "achievements"
    action = "view"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        info = access.get_access(self.request)
        canal = self.request.GET.get("canal", "")
        estado = self.request.GET.get("estado", "")

        base = tubos_del_alcance(self.request)
        if canal in TubeEntry.Channel.values:
            base = base.filter(channel=canal)
        else:
            canal = ""

        conteo = Counter(base.values_list("status", flat=True))
        validos = sum(n for st, n in conteo.items() if st != TubeEntry.Status.NOT_APPLICABLE)
        realizados = conteo.get(TubeEntry.Status.DONE, 0)
        porcentaje = round(realizados * 100 / validos, 1) if validos else None
        resumen = [(etiqueta, conteo.get(valor, 0)) for valor, etiqueta in TubeEntry.Status.choices]

        qs = base
        if estado in TubeEntry.Status.values:
            qs = qs.filter(status=estado)
        else:
            estado = ""
        pagina = Paginator(
            qs.select_related("delegation", "responsible__user"), POR_PAGINA,
        ).get_page(self.request.GET.get("page"))

        active = access.get_active_delegation(self.request)
        delegaciones, responsables = [], []
        if info.can("achievements", "create"):
            delegaciones = access.allowed_delegations(self.request.user)
            responsables = Employee.objects.filter(
                deleted_at__isnull=True, user__is_active=True,
                delegation_id__in=[d.pk for d in delegaciones],
            ).select_related("user", "delegation").order_by("delegation__name", "user__first_name")

        context.update({
            "active_module": "achievements",
            "module_label": MODULE_LABELS["achievements"],
            "module_icon": MODULE_ICONS["achievements"],
            "pagina": pagina,
            "canal": canal,
            "estado": estado,
            "canales": TubeEntry.Channel.choices,
            "estados": TubeEntry.Status.choices,
            "estados_editables": ESTADOS_EDITABLES,
            "resumen": resumen,
            "porcentaje": porcentaje,
            "querystring": urlencode({k: v for k, v in (("canal", canal), ("estado", estado)) if v}),
            "can_create": info.can("achievements", "create"),
            "can_edit": info.can("achievements", "edit"),
            "delegaciones": delegaciones,
            "responsables": responsables,
            "activa_pk": active.pk if active not in (None, access.ALL_DELEGATIONS) else None,
            "hoy": timezone.localdate().isoformat(),
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
            messages.success(request, f"Solicitud {entrada.code} ingresada. Código de verificación: {entrada.verification_code}.")
        else:
            messages.error(request, f"No se pudo ingresar la solicitud: {_errores(form)}")
        return redirect("tubes")


class TubeStatusView(LoginRequiredMixin, ModulePermissionMixin, View):
    """Cambia el estatus de una solicitud (sin llegar a Realizado)."""

    module = "achievements"
    action = "edit"

    def post(self, request, entry_id):
        entrada = get_object_or_404(tubos_del_alcance(request), pk=entry_id)
        nuevo = request.POST.get("status", "")
        if entrada.status == TubeEntry.Status.DONE:
            messages.info(request, f"{entrada.code} ya está realizada.")
        elif nuevo not in dict(ESTADOS_EDITABLES):
            messages.error(request, "Estatus no válido. Para marcar como Realizado hay que cerrar con foto y código.")
        else:
            entrada.status = nuevo
            entrada.save(update_fields=["status", "updated_at"])
            audit(request, "edit", module="achievements",
                object_repr=f"Tubo {entrada.code}", detail=f"Estatus: {entrada.get_status_display()}")
            messages.success(request, f"{entrada.code}: estatus actualizado.")
        return redirect("tubes")


class TubeCloseView(LoginRequiredMixin, ModulePermissionMixin, View):
    """Cierra una solicitud como Realizada con foto de respaldo y código de verificación."""

    module = "achievements"
    action = "edit"

    def post(self, request, entry_id):
        entrada = get_object_or_404(tubos_del_alcance(request), pk=entry_id)
        if entrada.status == TubeEntry.Status.DONE:
            messages.info(request, f"{entrada.code} ya está realizada.")
            return redirect("tubes")
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
        return redirect("tubes")