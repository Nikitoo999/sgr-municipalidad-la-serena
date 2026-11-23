"""Atenciones (Unidad 3): validación del punto, funcionario solicitante y comentarios.

- **Validación del punto** (RN-009, RF-013, CA-01/CA-02): el delegado o un rol
  superior aprueba, rechaza o pide corrección, con observación. Solo una
  atención aprobada aporta a la matriz. Nadie valida lo que registró.
- **Funcionario como civil**: búsqueda por RUT para avisar en el formulario
  que la persona es funcionaria (el servidor vuelve a validarlo al guardar).
- **Organizaciones y directiva**: búsqueda JSON de organizaciones y de los
  integrantes de su organigrama, para el ingreso "Directivo de organización".
- **Comentarios por registro** (RF-035 / HU-24): observaciones con autor y fecha.
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import redirect
from django.views import View

from operaciones import rules
from operaciones.models import RecordComment
from portal.validators import validate_rut
from sgr_core.models import CommunityOrganization, OrganizationMember

from ..access import ALL_DELEGATIONS, ModulePermissionMixin, allowed_delegations, get_active_delegation, get_role
from ..audit import audit
from .search import apply_search
from .views import CrudBaseMixin, resolve_object_or_deny, scoped_queryset

#: Largo máximo de un comentario.
COMMENT_MAX = 1000


class AttentionReviewView(LoginRequiredMixin, ModulePermissionMixin, CrudBaseMixin, View):
    """Aprueba, rechaza o pide corrección de una atención (solo POST)."""

    action = "edit"

    def get(self, request, *args, **kwargs):
        raise Http404("Registro inexistente.")

    def post(self, request, *args, **kwargs):
        queryset = scoped_queryset(request, self.config)
        attention = resolve_object_or_deny(request, self.config, queryset, self.kwargs["pk"])
        decision = request.POST.get("decision", "")
        notes = " ".join((request.POST.get("notes") or "").split())[:500]
        error = rules.attention_review_error(attention, request.user, decision, notes)
        if error:
            messages.error(request, error)
            return redirect("attentions_detail", pk=attention.pk)
        rules.apply_attention_review(attention, request.user, decision, notes)
        label = attention.get_validation_status_display()
        audit(
            request, "validate", module="attentions", object_repr=str(attention),
            detail=f"Validación: {label}" + (f" · {notes}" if notes else ""),
        )
        if decision == "approved":
            messages.success(request, f"Atención {attention.number} aprobada: ya aporta a la matriz.")
        else:
            messages.success(
                request, f"Atención {attention.number}: {label.lower()}. El funcionario verá tu observación.",
            )
        return redirect("attentions_detail", pk=attention.pk)


class AttentionRutCheckView(LoginRequiredMixin, ModulePermissionMixin, View):
    """¿El RUT del solicitante es el de un funcionario? (JSON, para el formulario).

    Solo responde con un RUT completo y válido (no permite enumerar por
    fragmentos). El servidor vuelve a comprobarlo al guardar la atención.
    """

    module = "attentions"
    action = "create"

    def get(self, request):
        try:
            rut = validate_rut(request.GET.get("rut", ""))
        except ValidationError:
            return JsonResponse({"employee": None})
        employee = rules.employee_for_rut(rut)
        if employee is None:
            return JsonResponse({"employee": None})
        return JsonResponse({"employee": {
            "name": employee.full_name,
            "delegation": f"{employee.delegation.code} · {employee.delegation.name}",
            "position": employee.position.name if employee.position_id else "Sin cargo",
            "is_self": employee.user_id == request.user.pk,
        }})


def _organizations_for(request):
    """Organizaciones activas visibles para el usuario (por delegación)."""
    qs = CommunityOrganization.alive.filter(status="Activo").select_related("delegation")
    role = get_role(request.user)
    if role is None:
        return qs.none()
    active = get_active_delegation(request)
    if active is not None and active != ALL_DELEGATIONS:
        return qs.filter(Q(delegation_id=active.pk) | Q(delegation__isnull=True))
    if role.scope == "all":
        return qs
    pks = [d.pk for d in allowed_delegations(request.user)]
    return qs.filter(Q(delegation_id__in=pks) | Q(delegation__isnull=True))


class OrganizationLookupView(LoginRequiredMixin, ModulePermissionMixin, View):
    """Búsqueda JSON de organizaciones (máx. 10) para el ingreso de atención o tubo."""

    module = "attentions"
    action = "view"

    def get(self, request):
        query = (request.GET.get("q") or "").strip()[:60]
        if len(query) < 2:
            return JsonResponse({"results": []})
        qs = apply_search(_organizations_for(request), ("name", "territory", "registry_number"), query)
        results = [
            {
                "pk": org.pk,
                "label": org.name,
                "detail": " · ".join(filter(None, [
                    org.get_category_display(),
                    org.delegation.code if org.delegation_id else "",
                    org.territory,
                ])),
            }
            for org in qs.order_by("name")[:10]
        ]
        return JsonResponse({"results": results})


class OrganizationMembersView(LoginRequiredMixin, ModulePermissionMixin, View):
    """Integrantes del organigrama de una organización (JSON)."""

    module = "attentions"
    action = "view"

    def get(self, request, pk):
        organization = _organizations_for(request).filter(pk=pk).first()
        if organization is None:
            raise Http404("Organización inexistente.")
        members = OrganizationMember.alive.filter(organization=organization).select_related("role")
        return JsonResponse({"members": [
            {
                "pk": m.pk, "name": m.full_name, "rut": m.rut, "phone": m.phone,
                "role_id": m.role_id, "role": m.role.name,
            }
            for m in members
        ]})


class AttentionCommentCreateView(LoginRequiredMixin, ModulePermissionMixin, CrudBaseMixin, View):
    """Agrega un comentario a una atención visible para el usuario (solo POST)."""

    action = "view"

    def get(self, request, *args, **kwargs):
        raise Http404("Registro inexistente.")

    def post(self, request, *args, **kwargs):
        queryset = scoped_queryset(request, self.config)
        attention = resolve_object_or_deny(request, self.config, queryset, self.kwargs["pk"])
        text = (request.POST.get("text") or "").strip()
        if len(text) < 2:
            messages.error(request, "Escribe el comentario antes de enviarlo.")
        elif len(text) > COMMENT_MAX:
            messages.error(request, f"El comentario no puede superar los {COMMENT_MAX} caracteres.")
        else:
            RecordComment.objects.create(attention=attention, author=request.user, text=text)
            audit(request, "comment", module="attentions", object_repr=str(attention),
                  detail=f"Comentario de {request.user}")
            messages.success(request, "Comentario agregado.")
        return redirect("attentions_detail", pk=attention.pk)


def review_context(request, attention, can_edit):
    """Datos de la validación del punto para la consulta de la atención."""
    status = attention.validation_status
    badge = {"approved": "b-ok", "rejected": "b-bad", "correction": "b-warn"}.get(status, "b-info")
    verifier = rules.is_verifier(request.user) and can_edit
    if not verifier:
        block = ""
    elif attention.responsible_id == request.user.pk:
        block = "Esta atención la registraste tú: debe validarla otro verificador."
    else:
        block = ""
    return {
        "validation": {
            "status": status,
            "label": attention.get_validation_status_display(),
            "badge": badge,
            "by": (
                (attention.validated_by.get_full_name() or attention.validated_by.username)
                if attention.validated_by_id else ""
            ),
            "at": attention.validated_at,
            "notes": attention.validation_notes,
            "has_evidence": bool(attention.evidence_image or attention.attachment),
        },
        "can_review": verifier and not block,
        "review_block_reason": block,
        "comments": list(attention.comments.filter(deleted_at__isnull=True).select_related("author")),
        "can_comment": True,
    }
