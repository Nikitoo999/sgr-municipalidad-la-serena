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
})();
