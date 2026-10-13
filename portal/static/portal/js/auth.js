/**
 * auth.js — JavaScript ligero para autenticación
 * - Mostrar/ocultar contraseña
 * - Validación en línea de campos vacíos
 * - Foco al primer error
 * - Deshabilitar botón al enviar
 * - Accesibilidad: aria-live, foco visible
 */
(function () {
  'use strict';

  // ---- Mostrar/ocultar contraseña ----
  function setupToggle(btnId, inputId) {
    var btn = document.getElementById(btnId);
    var inp = document.getElementById(inputId);
    if (!btn || !inp) return;
    btn.addEventListener('click', function () {
      var h = inp.type === 'password';
      inp.type = h ? 'text' : 'password';
      this.textContent = h ? 'Ocultar' : 'Mostrar';
      this.setAttribute('aria-pressed', h ? 'true' : 'false');
      inp.focus();
    });
  }
  setupToggle('togglePw', 'id_password');
  setupToggle('toggleNewPw', 'id_new_password');
  setupToggle('toggleConfirmPw', 'id_confirm_password');

  // ---- Login: validación en línea y deshabilitar botón ----
  var loginForm = document.getElementById('loginForm');
  if (loginForm) {
    loginForm.addEventListener('submit', function (e) {
      var u = document.getElementById('id_username');
      var p = document.getElementById('id_password');
      var uErr = document.getElementById('username-error');
      var pErr = document.getElementById('password-error');
      var bad = false;

      // Limpiar errores previos
      if (uErr) uErr.innerHTML = '';
      if (pErr) pErr.innerHTML = '';
      u.removeAttribute('aria-invalid');
      p.removeAttribute('aria-invalid');

      if (!u.value.trim()) {
        if (uErr) uErr.innerHTML = '<div class="err">Ingresa tu usuario o correo.</div>';
        u.setAttribute('aria-invalid', 'true');
        bad = true;
      }
      if (!p.value) {
        if (pErr) pErr.innerHTML = '<div class="err">Ingresa tu contraseña.</div>';
        p.setAttribute('aria-invalid', 'true');
        bad = true;
      }
      if (bad) {
        e.preventDefault();
        (u.value.trim() ? p : u).focus();
        return;
      }

      // Deshabilitar botón al enviar
      var btn = document.getElementById('loginBtn');
      if (btn) { btn.disabled = true; btn.textContent = 'Verificando…'; }
    });
  }

  // ---- Paso 1 recuperación: validación en línea ----
  var recoverForm = document.getElementById('recoverForm');
  if (recoverForm) {
    recoverForm.addEventListener('submit', function (e) {
      var i = document.getElementById('id_email');
      var err = document.getElementById('email-error');
      var v = i.value.trim();
      err.innerHTML = '';
      i.removeAttribute('aria-invalid');

      if (!v) {
        err.innerHTML = '<div class="err">Ingresa tu correo electrónico.</div>';
        i.setAttribute('aria-invalid', 'true');
        i.focus();
        e.preventDefault();
        return;
      }
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v)) {
        err.innerHTML = '<div class="err">Ingresa un correo válido, por ejemplo nombre@dominio.cl.</div>';
        i.setAttribute('aria-invalid', 'true');
        i.focus();
        e.preventDefault();
        return;
      }

      var btn = document.getElementById('sendBtn');
      if (btn) { btn.disabled = true; btn.textContent = 'Enviando…'; }
    });
  }

  // ---- Casillas del código (paso 2) ----
  // Se maneja en el template step2.html porque necesita datos del servidor

})();
