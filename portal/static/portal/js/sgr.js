/**
 * sgr.js — JavaScript ligero del shell (Parte 3).
 * - Menú móvil, anti-doble-envío, cambio de delegación y confirmación de salida.
 */
(function () {
  'use strict';

  // ---- Menú móvil ----
  var mb = document.getElementById('menuBtn');
  if (mb) {
    mb.addEventListener('click', function () {
      var open = document.body.classList.toggle('nav-open');
      mb.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
    document.querySelectorAll('.nav a').forEach(function (l) {
      l.addEventListener('click', function () {
        document.body.classList.remove('nav-open');
      });
    });
  }

  // ---- Deshabilitar botón al enviar (sin doble envío) ----
  document.querySelectorAll('form').forEach(function (form) {
    form.addEventListener('submit', function () {
      var btn = form.querySelector('[type="submit"]');
      if (btn && !btn.disabled && !form.dataset.noDisable) {
        btn.disabled = true;
        if (btn.dataset.label === undefined) btn.dataset.label = btn.textContent;
        btn.textContent = 'Enviando…';
      }
    });
  });

  // ---- Cambio de delegación activa (POST inmediato) ----
  var ctx = document.getElementById('ctxSel');
  if (ctx) {
    ctx.addEventListener('change', function () {
      var form = document.getElementById('ctxForm');
      if (form) form.submit();
    });
  }

  // ---- Salir pide confirmación con SweetAlert ----
  var logoutForm = document.getElementById('logoutForm');
  if (logoutForm) {
    logoutForm.dataset.noDisable = '1';
    logoutForm.addEventListener('submit', function (e) {
      e.preventDefault();
      Swal.fire({
        icon: 'question',
        title: '¿Cerrar sesión?',
        text: 'Tendrás que ingresar de nuevo para continuar.',
        showCancelButton: true,
        confirmButtonText: 'Cerrar sesión',
        cancelButtonText: 'Cancelar',
        confirmButtonColor: '#920000'
      }).then(function (result) {
        if (result.isConfirmed) logoutForm.submit();
      });
    });
  }
  // ---- Mini menú de usuario (cabecera) ----
  var userMenuBtn = document.getElementById('userMenuBtn');
  var userDropdown = document.getElementById('userDropdown');
  if (userMenuBtn && userDropdown) {
    var closeUserMenu = function () {
      userDropdown.hidden = true;
      userMenuBtn.setAttribute('aria-expanded', 'false');
    };
    userMenuBtn.addEventListener('click', function (e) {
      e.stopPropagation();
      var opening = userDropdown.hidden;
      userDropdown.hidden = !opening;
      userMenuBtn.setAttribute('aria-expanded', opening ? 'true' : 'false');
    });
    document.addEventListener('click', function (e) {
      if (!userMenuBtn.contains(e.target) && !userDropdown.contains(e.target)) {
        closeUserMenu();
      }
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') closeUserMenu();
    });
    userDropdown.addEventListener('click', function (e) {
      if (e.target.closest('.user-dropdown-item')) closeUserMenu();
    });
  }

  // ---- Modal de perfil ----
  var profileModal = document.getElementById('profileModal');
  var openProfileBtn = document.getElementById('openProfileModalBtn');
  var closeProfileBtn = document.getElementById('closeProfileModalBtn');
  var openModal = function () {};
  var closeModal = function () {};
  if (profileModal && openProfileBtn && closeProfileBtn) {
    openModal = function () {
      profileModal.hidden = false;
      document.body.style.overflow = 'hidden';
    };
    closeModal = function () {
      profileModal.hidden = true;
      document.body.style.overflow = '';
    };
    openProfileBtn.addEventListener('click', openModal);
    closeProfileBtn.addEventListener('click', closeModal);
    profileModal.addEventListener('click', function (e) {
      if (e.target === profileModal) closeModal();
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && !profileModal.hidden) closeModal();
    });
  }

  // ---- Pestañas del modal ----
  var tabContact = document.getElementById('tabContactBtn');
  var tabSecurity = document.getElementById('tabSecurityBtn');
  var panelContact = document.getElementById('panel-contact');
  var panelSecurity = document.getElementById('panel-security');
  if (tabContact && tabSecurity && panelContact && panelSecurity) {
    var activateTab = function (tab, panel) {
      [tabContact, tabSecurity].forEach(function (t) {
        t.classList.toggle('active', t === tab);
        t.setAttribute('aria-selected', t === tab ? 'true' : 'false');
      });
      panelContact.hidden = panel !== panelContact;
      panelSecurity.hidden = panel !== panelSecurity;
    };
    tabContact.addEventListener('click', function () { activateTab(tabContact, panelContact); });
    tabSecurity.addEventListener('click', function () { activateTab(tabSecurity, panelSecurity); });
  }

  // ---- Mostrar/ocultar contraseña en el modal ----
  document.querySelectorAll('#profileModal [data-toggle]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var input = document.getElementById(btn.dataset.toggle);
      if (!input) return;
      var hidden = input.type === 'password';
      input.type = hidden ? 'text' : 'password';
      btn.textContent = hidden ? 'Ocultar' : 'Mostrar';
      btn.setAttribute('aria-pressed', hidden ? 'true' : 'false');
    });
  });

  // ---- Requisitos en vivo de la nueva contraseña ----
  var newPw = document.getElementById('pf_new_password');
  if (newPw) {
    var setReq = function (id, ok) {
      var el = document.getElementById(id);
      if (!el) return;
      el.dataset.ok = ok ? 'true' : 'false';
      el.classList.toggle('ok', ok);
    };
    var checkReqs = function () {
      var v = newPw.value;
      setReq('pf-req-len', v.length >= 8);
      setReq('pf-req-upper', /[A-Z]/.test(v));
      setReq('pf-req-lower', /[a-z]/.test(v));
      setReq('pf-req-digit', /[0-9]/.test(v));
    };
    newPw.addEventListener('input', checkReqs);
  }

  // ---- Envío AJAX de los formularios del modal ----
  var clearErrors = function (form) {
    form.querySelectorAll('.pf-err').forEach(function (el) { el.textContent = ''; });
    form.querySelectorAll('[aria-invalid="true"]').forEach(function (el) { el.removeAttribute('aria-invalid'); });
  };
  var showErrors = function (form, errors) {
    Object.keys(errors || {}).forEach(function (name) {
      var slot = form.querySelector('[id="' + name + '-e"]');
      var input = form.querySelector('[name="' + name + '"]');
      if (slot) slot.textContent = errors[name];
      if (input) input.setAttribute('aria-invalid', 'true');
    });
  };
  var bindModalForm = function (formId, onSuccess) {
    var form = document.getElementById(formId);
    if (!form) return;
    form.dataset.noDisable = '1';
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      clearErrors(form);
      var submitBtn = form.querySelector('[type="submit"]');
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.dataset.label = submitBtn.textContent;
        submitBtn.textContent = 'Guardando…';
      }
      fetch(form.action, {
        method: 'POST',
        body: new FormData(form),
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
      }).then(function (resp) {
        return resp.json().then(function (data) { return { status: resp.status, data: data }; });
      }).then(function (res) {
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.textContent = submitBtn.dataset.label || submitBtn.textContent;
        }
        if (res.data && res.data.ok) {
          if (onSuccess) onSuccess(res.data);
        } else if (res.data && res.data.errors) {
          showErrors(form, res.data.errors);
        } else {
          Swal.fire({ icon: 'error', title: 'Error', text: 'No se pudo completar la operación.', confirmButtonColor: '#920000' });
        }
      }).catch(function () {
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.textContent = submitBtn.dataset.label || submitBtn.textContent;
        }
        Swal.fire({ icon: 'error', title: 'Error', text: 'No se pudo completar la operación.', confirmButtonColor: '#920000' });
      });
    });
  };

  bindModalForm('contactForm', function (data) {
    if (data.display_name) {
      var nameEl = document.querySelector('.who-tx strong');
      if (nameEl) nameEl.textContent = data.display_name;
    }
    closeModal();
    Swal.fire({ icon: 'success', title: 'Perfil actualizado', text: data.message || '', confirmButtonColor: '#920000' });
  });

  bindModalForm('passwordForm', function (data) {
    closeModal();
    Swal.fire({ icon: 'success', title: 'Contraseña actualizada', text: data.message || '', confirmButtonColor: '#920000' });
  });
})();
