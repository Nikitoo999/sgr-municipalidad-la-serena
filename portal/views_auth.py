import secrets
import logging
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.views import LoginView
from django.core.mail import send_mail
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac
from django.views.decorators.http import require_POST

from .access import active_delegation, allowed_delegations, get_employee
from .forms import LoginForm, ResetCodeForm, ResetRequestForm
from .models import PasswordResetCode

User = get_user_model()
log = logging.getLogger(__name__)

TTL = getattr(settings, "PASSWORD_RESET_TTL_SECONDS", 600)          # vigencia del código (10 min)
RESEND = getattr(settings, "PASSWORD_RESET_RESEND_SECONDS", 45)     # espera entre envíos
MAX_ATTEMPTS = getattr(settings, "PASSWORD_RESET_MAX_ATTEMPTS", 5)  # intentos por código
MAX_PER_HOUR = getattr(settings, "PASSWORD_RESET_MAX_PER_HOUR", 5)  # códigos por usuario/hora
GENERIC_SENT = "Si la cuenta existe, recibirás un código en tu correo. Revisa también tu carpeta de spam."
GENERIC_BAD_CODE = "El código es incorrecto o ha vencido. Verifica los dígitos o solicita uno nuevo."


class SgrLoginView(LoginView):
    template_name = "portal/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        response = super().form_valid(form)
        deleg = active_delegation(self.request)
        self.request.session["active_delegation_id"] = deleg.pk if deleg else None
        return response


@require_POST
def switch_delegation(request):
    if not request.user.is_authenticated:
        return redirect("login")
    target = allowed_delegations(request.user, only_active=True).filter(pk=request.POST.get("delegation") or 0).first()
    if target is None:
        messages.error(request, "No tienes autorización para operar en esa delegación.")
    else:
        request.session["active_delegation_id"] = target.pk
        messages.success(request, f"Delegación activa: {target}.")
    return redirect(request.POST.get("next") or "dashboard")


# ---------------------------- Recuperación de contraseña ----------------------------
def _hash(user_id, code):
    return salted_hmac("sgr.password_reset", f"{user_id}:{code}").hexdigest()


def _issue_code(email):
    """Genera y envía un código. Silencioso: nunca revela si el correo existe."""
    users = list(User.objects.filter(email__iexact=email, is_active=True)[:2])
    if len(users) != 1:
        return
    user = users[0]
    if user.is_superuser is False and get_employee(user) is None:
        return
    now = timezone.now()
    recent = PasswordResetCode.objects.filter(user=user, created_at__gte=now - timedelta(hours=1))
    last = recent.first()
    if last and (now - last.created_at).total_seconds() < RESEND:
        return
    if recent.count() >= MAX_PER_HOUR:
        return
    PasswordResetCode.objects.filter(user=user, used_at__isnull=True).update(used_at=now)  # invalida anteriores
    code = f"{secrets.randbelow(10**6):06d}"
    PasswordResetCode.objects.create(user=user, code_hash=_hash(user.pk, code), expires_at=now + timedelta(seconds=TTL))
    try:
        send_mail(
            "Código de recuperación de contraseña - SGR La Serena",
            f"Tu código es: {code}\n\nVence en {TTL // 60} minutos. Si no lo solicitaste, ignora este mensaje.",
            None, [user.email], fail_silently=False)
    except Exception:  # el usuario no debe ver detalles técnicos
        log.exception("No se pudo enviar el correo de recuperación")


def password_reset_request(request):
    form = ResetRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"].strip().lower()
        _issue_code(email)
        request.session["pr_email"] = email
        request.session["pr_sent_at"] = timezone.now().timestamp()
        request.session.pop("pr_code_id", None)
        messages.info(request, GENERIC_SENT)
        return redirect("password_reset_verify")
    return render(request, "portal/password_reset_request.html", {"form": form})


def _resend_wait(request):
    sent = request.session.get("pr_sent_at") or 0
    return max(0, int(RESEND - (timezone.now().timestamp() - sent)))


def password_reset_verify(request):
    email = request.session.get("pr_email")
    if not email:
        return redirect("password_reset_request")
    form = ResetCodeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        now = timezone.now()
        user = User.objects.filter(email__iexact=email, is_active=True).first()
        prc = (PasswordResetCode.objects.filter(user=user, used_at__isnull=True).first()) if user else None
        ok = False
        if prc and prc.expires_at > now and prc.attempts < MAX_ATTEMPTS:
            if constant_time_compare(prc.code_hash, _hash(user.pk, form.cleaned_data["code"])):
                ok = True
            else:
                prc.attempts += 1
                if prc.attempts >= MAX_ATTEMPTS:
                    prc.used_at = now  # bloqueado: hay que pedir otro código
                prc.save(update_fields=["attempts", "used_at"])
        if ok:
            prc.verified_at = now
            prc.save(update_fields=["verified_at"])
            request.session["pr_code_id"] = prc.pk
            return redirect("password_reset_confirm")
        form.add_error(None, GENERIC_BAD_CODE)
    return render(request, "portal/password_reset_verify.html", {
        "form": form, "ttl_minutes": TTL // 60, "resend_wait": _resend_wait(request),
        "masked_email": _mask(email)})


def _mask(email):
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}"


@require_POST
def password_reset_resend(request):
    email = request.session.get("pr_email")
    if not email:
        return redirect("password_reset_request")
    wait = _resend_wait(request)
    if wait:
        messages.warning(request, f"Podrás reenviar el código en {wait} segundos.")
    else:
        _issue_code(email)
        request.session["pr_sent_at"] = timezone.now().timestamp()
        messages.info(request, GENERIC_SENT)
    return redirect("password_reset_verify")


def password_reset_confirm(request):
    """Solo accesible tras verificar un código válido (la sesión guarda el id verificado)."""
    now = timezone.now()
    prc = PasswordResetCode.objects.select_related("user").filter(
        pk=request.session.get("pr_code_id") or 0, verified_at__isnull=False,
        used_at__isnull=True, expires_at__gt=now).first()
    if prc is None:
        messages.error(request, "Primero debes verificar un código válido.")
        return redirect("password_reset_request")
    form = SetPasswordForm(prc.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            form.save()
            PasswordResetCode.objects.filter(user=prc.user, used_at__isnull=True).update(used_at=now)
        for key in ("pr_code_id", "pr_email", "pr_sent_at"):
            request.session.pop(key, None)
        messages.success(request, "Tu contraseña fue actualizada. Ya puedes iniciar sesión.")
        return redirect("login")
    return render(request, "portal/password_reset_confirm.html", {"form": form})
