"""Tubos de trabajo: delegación, Antena y Cartas, con estados y código de verificación (3.6).

Unidad 3 (formato Card / modelo Canvas): la vista por defecto es un tablero de
cuatro columnas (Ingresados, Pendientes, En proceso, Realizados) con cuatro
indicadores arriba; la planilla (tabla paginada) sigue disponible.

Agenda colectiva según la Guía (RF-016 a RF-021):

- Cada cambio queda en el historial (``TubeStatusChange``): estado anterior y
  nuevo, autor, fecha y observación (RF-018).
- Plazos (RF-019): vencidos y próximos a vencer destacados; los realizados
  después de la fecha comprometida se marcan "fuera de plazo". Reprogramar
  exige motivo ("informar al usuario cuando no podemos cumplir en fecha").
- Reasignación con motivo (HU-15) y comentarios por solicitud (RF-035).
- Resumen colectivo por funcionario y delegación con la exigencia del 80 %
  (RF-021, diapositiva 14 de la presentación de la matriz).
"""
from collections import Counter, defaultdict
from datetime import timedelta
from urllib.parse import urlencode

from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import TemplateView

from operaciones import rules
from operaciones.models import Employee, RecordComment, TubeEntry, TubeStatusChange
from sgr_core.models import CommunityOrganization, Delegation

from . import access
from .period_context import operational_records
from .access import ModulePermissionMixin
from .audit import audit
from .modal import ModalFormMixin
from .modules import MODULE_ICONS, MODULE_LABELS

POR_PAGINA = 25
#: Tarjetas por columna en el tablero (el resto se consulta en la planilla).
POR_COLUMNA = 60
#: Días antes del compromiso en que una solicitud se marca "próxima a vencer".
DIAS_PROXIMO_A_VENCER = 3
#: Porcentaje de solicitudes realizadas que exige la matriz (diapositiva 14).
UMBRAL_TUBO = 80
#: "Realizado" solo se alcanza cerrando con foto y código de verificación.
ESTADOS_EDITABLES = [
    (valor, etiqueta) for valor, etiqueta in TubeEntry.Status.choices
    if valor != TubeEntry.Status.DONE
]
ABIERTOS = (TubeEntry.Status.RECEIVED, TubeEntry.Status.PENDING, TubeEntry.Status.IN_PROGRESS)
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
#: Largo mínimo del motivo al reprogramar o reasignar.
MOTIVO_MIN = 5


def tubos_del_alcance(request):
    """Solicitudes visibles según rol y delegación activa."""
    role = access.get_role(request.user)
    active = access.get_active_delegation(request)
    qs = TubeEntry.alive.filter(source_task__deleted_at__isnull=True)
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


def marcar_plazos(entrada, hoy):
    """Marca vencida / próxima a vencer / fuera de plazo (RF-019)."""
    abierta = entrada.status in ABIERTOS
    due = entrada.due_date
    entrada.vencida = bool(due and abierta and due < hoy)
    entrada.proxima = bool(due and abierta and hoy <= due <= hoy + timedelta(days=DIAS_PROXIMO_A_VENCER))
    entrada.fuera_de_plazo = bool(
        due and entrada.status == TubeEntry.Status.DONE and entrada.completed_at
        and timezone.localtime(entrada.completed_at).date() > due
    )
    return entrada


def resumen_por_funcionario(qs, hoy):
    """% realizado por funcionario y total de la delegación (RF-021).

    No cuentan las solicitudes "No aplica". Se compara con la exigencia del
    80 % de la matriz.
    """
    filas = defaultdict(lambda: {"total": 0, "realizadas": 0, "abiertas": 0, "vencidas": 0})
    datos = qs.exclude(status=TubeEntry.Status.NOT_APPLICABLE).values_list(
        "status", "due_date", "responsible_id",
        "responsible__user__first_name", "responsible__user__last_name", "responsible__user__username",
    )
    for status, due, resp_id, nombre, apellido, username in datos:
        fila = filas[resp_id or 0]
        fila["nombre"] = (f"{nombre} {apellido}".strip() or username) if resp_id else "Sin asignar"
        fila["total"] += 1
        if status == TubeEntry.Status.DONE:
            fila["realizadas"] += 1
        else:
            fila["abiertas"] += 1
            if due and due < hoy:
                fila["vencidas"] += 1
    lista = sorted(filas.values(), key=lambda f: f["nombre"])
    total = {"nombre": "Total delegación", "total": 0, "realizadas": 0, "abiertas": 0, "vencidas": 0}
    for fila in lista:
        for clave in ("total", "realizadas", "abiertas", "vencidas"):
            total[clave] += fila[clave]
    for fila in lista + [total]:
        fila["pct"] = _pct(fila["realizadas"], fila["total"])
        fila["cumple"] = fila["pct"] is not None and fila["pct"] >= UMBRAL_TUBO
    return lista, total


def registrar_cambio(entrada, kind, user, de="", a="", notas=""):
    """Agrega una fila al historial de la solicitud (RF-018)."""
    return TubeStatusChange.objects.create(
        entry=entrada, kind=kind, from_value=str(de or "")[:80], to_value=str(a or "")[:80],
        notes=(notas or "").strip(), changed_by=user if getattr(user, "is_authenticated", False) else None,
    )


class TubeListView(LoginRequiredMixin, ModulePermissionMixin, TemplateView):
    template_name = "portal/tubes.html"
    module = "achievements"
    action = "view"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        info = access.get_access(self.request)
        canal = self.request.GET.get("canal", "")
        estado = self.request.GET.get("estado", "")
        prio = self.request.GET.get("prio", "")
        vista = self.request.GET.get("vista", "")
        if vista not in VISTAS:
            vista = VISTAS[0]

        base = operational_records(self.request)["tubes"]
        if canal in TubeEntry.Channel.values:
            base = base.filter(channel=canal)
        else:
            canal = ""
        if prio == "1":
            base = base.filter(priority=True)
        else:
            prio = ""

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
        qs = qs.select_related("delegation", "responsible__user", "organization")

        hoy = timezone.localdate()
        columnas, pagina = [], None
        if vista == "tablero":
            for valor, titulo, css in COLUMNAS_TABLERO:
                if estado and estado != valor:
                    continue
                orden = ("-completed_at", "-pk") if valor == TubeEntry.Status.DONE else ("-priority", "due_date", "request_date", "pk")
                tarjetas = list(qs.filter(status=valor).order_by(*orden)[:POR_COLUMNA])
                for tarjeta in tarjetas:
                    tarjeta.siguiente = SIGUIENTE_ESTADO.get(tarjeta.status)
                    marcar_plazos(tarjeta, hoy)
                columnas.append({
                    "estado": valor, "titulo": titulo, "css": css,
                    "tarjetas": tarjetas, "total": conteo.get(valor, 0),
                })
        else:
            pagina = Paginator(qs, POR_PAGINA).get_page(self.request.GET.get("page"))
            for entrada in pagina:
                marcar_plazos(entrada, hoy)
        filas_resumen, total_resumen = resumen_por_funcionario(base, hoy)

        active = access.get_active_delegation(self.request)
        delegaciones, responsables = [], []
        if info.can("achievements", "create"):
            delegaciones = access.allowed_delegations(self.request.user)
            responsables = Employee.objects.filter(
                deleted_at__isnull=True, user__is_active=True,
                delegation_id__in=[d.pk for d in delegaciones],
            ).select_related("user", "delegation").order_by("delegation__name", "user__first_name")

        filtros = {k: v for k, v in (("canal", canal), ("estado", estado), ("prio", prio)) if v}
        context.update({
            "active_module": "achievements",
            "module_label": MODULE_LABELS["achievements"],
            "module_icon": MODULE_ICONS["achievements"],
            "vista": vista,
            "columnas": columnas,
            "indicadores": indicadores(conteo),
            "sin_registros": not conteo or (estado and not conteo.get(estado)),
            "no_aplica": conteo.get(TubeEntry.Status.NOT_APPLICABLE, 0),
            "pagina": pagina,
            "canal": canal,
            "estado": estado,
            "prio": prio,
            "canales": TubeEntry.Channel.choices,
            "estados": TubeEntry.Status.choices,
            "estados_editables": ESTADOS_EDITABLES,
            "resumen": resumen,
            "porcentaje": porcentaje,
            "filas_resumen": filas_resumen,
            "total_resumen": total_resumen,
            "umbral_tubo": UMBRAL_TUBO,
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
            "organization",
        ]

    def __init__(self, *args, delegations=(), **kwargs):
        super().__init__(*args, **kwargs)
        pks = [d.pk for d in delegations]
        self.fields["delegation"].queryset = Delegation.objects.filter(pk__in=pks)
        self.fields["responsible"].queryset = Employee.objects.filter(
            deleted_at__isnull=True, user__is_active=True, delegation_id__in=pks,
        )
        self.fields["organization"].queryset = CommunityOrganization.alive.all()
        self.fields["organization"].required = False

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
        organizacion = cleaned.get("organization")
        if (delegacion and organizacion and organizacion.delegation_id
                and organizacion.delegation_id != delegacion.pk):
            self.add_error("organization", "La organización pertenece a otra delegación.")
        solicitud, compromiso = cleaned.get("request_date"), cleaned.get("due_date")
        if solicitud and compromiso and compromiso < solicitud:
            self.add_error("due_date", "La fecha de compromiso no puede ser anterior a la solicitud.")
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
    """Vuelve al tablero, planilla o detalle de origen (con sus filtros) si es seguro."""
    destino = request.POST.get("next", "")
    if destino and url_has_allowed_host_and_scheme(
        destino, allowed_hosts={request.get_host()}, require_https=request.is_secure(),
    ) and destino.startswith(reverse("tubes")):
        return redirect(destino)
    return redirect("tubes")


def _es_ajax(request):
    return request.headers.get("x-requested-with") == "XMLHttpRequest"


def _nombre(employee):
    return employee.full_name if employee is not None else "Sin asignar"


class TubeCreateView(LoginRequiredMixin, ModulePermissionMixin, View):
    """Ingresa una solicitud al tubo."""

    module = "achievements"
    action = "create"

    def post(self, request):
        form = TubeEntryForm(request.POST, delegations=access.allowed_delegations(request.user))
        if form.is_valid():
            entrada = form.save()
            registrar_cambio(entrada, TubeStatusChange.Kind.CREATED, request.user,
                             a=entrada.get_status_display(), notas=entrada.notes)
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


class TubeDetailView(ModalFormMixin, LoginRequiredMixin, ModulePermissionMixin, TemplateView):
    """Ficha de una solicitud: datos, historial, acciones y comentarios.

    Se abre como ventana emergente desde el tablero ("Ver") o como página.
    """

    template_name = "portal/tube_detail.html"
    module = "achievements"
    action = "view"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        entrada = get_object_or_404(
            tubos_del_alcance(self.request).select_related(
                "delegation", "responsible__user", "organization", "carried_to_period",
            ),
            pk=self.kwargs["entry_id"],
        )
        hoy = timezone.localdate()
        marcar_plazos(entrada, hoy)
        info = access.get_access(self.request)
        responsables = Employee.objects.filter(
            deleted_at__isnull=True, user__is_active=True, delegation_id=entrada.delegation_id,
        ).select_related("user").order_by("user__first_name", "user__last_name")
        context.update({
            "active_module": "achievements",
            "module_label": MODULE_LABELS["achievements"],
            "e": entrada,
            "historial": entrada.history.select_related("changed_by"),
            "comentarios": entrada.comments.filter(deleted_at__isnull=True).select_related("author"),
            "estados_editables": ESTADOS_EDITABLES,
            "responsables": responsables,
            "can_edit": info.can("achievements", "edit"),
            "volver": self.request.path,
            "hoy": hoy.isoformat(),
        })
        return context


class TubeStatusView(ModalFormMixin, LoginRequiredMixin, ModulePermissionMixin, View):
    """Cambia el estatus de una solicitud (sin llegar a Realizado).

    Desde el tablero (arrastrar y soltar) responde JSON; desde un formulario
    redirige de vuelta con un mensaje. Queda en el historial con observación.
    """

    module = "achievements"
    action = "edit"

    def post(self, request, entry_id):
        entrada = get_object_or_404(tubos_del_alcance(request), pk=entry_id)
        nuevo = request.POST.get("status", "")
        notas = " ".join((request.POST.get("notes") or "").split())[:500]
        ok, texto = False, ""
        if entrada.status == TubeEntry.Status.DONE:
            texto = f"{entrada.code} ya está realizada."
        elif nuevo not in dict(ESTADOS_EDITABLES):
            texto = "Estatus no válido. Para marcar como Realizado hay que cerrar con foto y código."
        else:
            ok = True
            if entrada.status != nuevo:
                anterior = entrada.get_status_display()
                entrada.status = nuevo
                entrada.save(update_fields=["status", "updated_at"])
                registrar_cambio(entrada, TubeStatusChange.Kind.STATUS, request.user,
                                 de=anterior, a=entrada.get_status_display(), notas=notas)
                audit(request, "edit", module="achievements",
                    object_repr=f"Tubo {entrada.code}", detail=f"Estatus: {anterior} → {entrada.get_status_display()}")
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


class TubeRescheduleView(ModalFormMixin, LoginRequiredMixin, ModulePermissionMixin, View):
    """Reprograma la fecha de compromiso con motivo (RF-019, diapositiva 13)."""

    module = "achievements"
    action = "edit"

    def post(self, request, entry_id):
        entrada = get_object_or_404(tubos_del_alcance(request), pk=entry_id)
        notas = " ".join((request.POST.get("notes") or "").split())[:500]
        campo = forms.DateField(required=True)
        try:
            nueva = campo.clean(request.POST.get("due_date"))
        except forms.ValidationError:
            nueva = None
        if entrada.status in (TubeEntry.Status.DONE, TubeEntry.Status.NOT_APPLICABLE):
            messages.error(request, f"{entrada.code} ya no está abierta: no se puede reprogramar.")
        elif nueva is None:
            messages.error(request, "Indica la nueva fecha de compromiso.")
        elif nueva < entrada.request_date:
            messages.error(request, "La nueva fecha no puede ser anterior a la fecha de solicitud.")
        elif len(notas) < MOTIVO_MIN:
            messages.error(request, "Indica el motivo de la reprogramación (y avisa al usuario).")
        else:
            anterior = entrada.due_date.strftime("%d-%m-%Y") if entrada.due_date else "Sin fecha"
            entrada.due_date = nueva
            entrada.save(update_fields=["due_date", "updated_at"])
            registrar_cambio(entrada, TubeStatusChange.Kind.RESCHEDULE, request.user,
                             de=anterior, a=nueva.strftime("%d-%m-%Y"), notas=notas)
            audit(request, "edit", module="achievements", object_repr=f"Tubo {entrada.code}",
                  detail=f"Compromiso {anterior} → {nueva:%d-%m-%Y}: {notas}")
            messages.success(request, f"{entrada.code}: compromiso reprogramado al {nueva:%d-%m-%Y}.")
        return _volver(request)


class TubeReassignView(ModalFormMixin, LoginRequiredMixin, ModulePermissionMixin, View):
    """Reasigna el responsable con motivo (HU-15: continuidad operativa)."""

    module = "achievements"
    action = "edit"

    def post(self, request, entry_id):
        entrada = get_object_or_404(
            tubos_del_alcance(request).select_related("responsible__user"), pk=entry_id,
        )
        notas = " ".join((request.POST.get("notes") or "").split())[:500]
        pk = request.POST.get("responsible", "")
        nuevo = None
        if pk.isdigit():
            nuevo = Employee.objects.filter(
                pk=int(pk), deleted_at__isnull=True, user__is_active=True,
                delegation_id=entrada.delegation_id,
            ).select_related("user").first()
        if entrada.status in (TubeEntry.Status.DONE, TubeEntry.Status.NOT_APPLICABLE):
            messages.error(request, f"{entrada.code} ya no está abierta: no se puede reasignar.")
        elif nuevo is None:
            messages.error(request, "Elige un funcionario activo de la misma delegación.")
        elif nuevo.pk == entrada.responsible_id:
            messages.info(request, f"{nuevo.full_name} ya es el responsable de {entrada.code}.")
        elif len(notas) < MOTIVO_MIN:
            messages.error(request, "Indica el motivo de la reasignación (vacaciones, licencia, carga...).")
        else:
            anterior = _nombre(entrada.responsible)
            entrada.responsible = nuevo
            entrada.save(update_fields=["responsible", "updated_at"])
            registrar_cambio(entrada, TubeStatusChange.Kind.REASSIGN, request.user,
                             de=anterior, a=nuevo.full_name, notas=notas)
            audit(request, "edit", module="achievements", object_repr=f"Tubo {entrada.code}",
                  detail=f"Responsable {anterior} → {nuevo.full_name}: {notas}")
            messages.success(request, f"{entrada.code}: reasignada a {nuevo.full_name}.")
        return _volver(request)


class TubeCommentView(ModalFormMixin, LoginRequiredMixin, ModulePermissionMixin, View):
    """Comentario asociado a una solicitud (RF-035)."""

    module = "achievements"
    action = "view"

    def post(self, request, entry_id):
        entrada = get_object_or_404(tubos_del_alcance(request), pk=entry_id)
        texto = (request.POST.get("text") or "").strip()
        if len(texto) < 2:
            messages.error(request, "Escribe el comentario antes de enviarlo.")
        elif len(texto) > 1000:
            messages.error(request, "El comentario no puede superar los 1000 caracteres.")
        else:
            RecordComment.objects.create(tube_entry=entrada, author=request.user, text=texto)
            messages.success(request, f"Comentario agregado a {entrada.code}.")
        return _volver(request)


class TubeCloseView(ModalFormMixin, LoginRequiredMixin, ModulePermissionMixin, View):
    """Cierra una solicitud como Realizada con foto de respaldo y código de verificación."""

    module = "achievements"
    action = "edit"

    def post(self, request, entry_id):
        entrada = get_object_or_404(tubos_del_alcance(request), pk=entry_id)
        if entrada.status == TubeEntry.Status.DONE:
            messages.info(request, f"{entrada.code} ya está realizada.")
            return _volver(request)
        anterior = entrada.get_status_display()
        form = TubeCloseForm(request.POST, request.FILES, instance=entrada)
        if form.is_valid():
            entrada = form.save(commit=False)
            entrada.status = TubeEntry.Status.DONE
            entrada.completed_at = timezone.now()
            entrada.priority = False
            entrada.save()
            fuera = bool(entrada.due_date and timezone.localdate() > entrada.due_date)
            registrar_cambio(entrada, TubeStatusChange.Kind.CLOSED, request.user,
                             de=anterior, a=entrada.get_status_display(),
                             notas="Realizada fuera de plazo." if fuera else "")
            audit(request, "edit", module="achievements",
                object_repr=f"Tubo {entrada.code}", detail=f"Cerrada con foto por {request.user}")
            messages.success(request, f"{entrada.code} cerrada como realizada.")
        else:
            messages.error(request, f"No se pudo cerrar {entrada.code}: {_errores(form)}")
        return _volver(request)

