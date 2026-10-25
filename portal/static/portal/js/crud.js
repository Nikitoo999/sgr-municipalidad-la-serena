/**
 * crud.js — JavaScript ligero de los mantenedores (Parte 4).
 * - Búsqueda/filtro: el campo de búsqueda se envía solo (sin botón, debounce
 *   de 350 ms); la X nativa y Enter envían de inmediato cancelando el
 *   temporizador; tras recargar vuelve el foco al campo con el cursor al final
 *   (marca en sessionStorage). En el listado compartido el estado se filtra con
 *   píldoras (enlaces GET, sin JavaScript), el selector de filas por página y
 *   los selects de la grilla de filtros del módulo envían su formulario al
 *   cambiar; en Atenciones el estado sigue siendo un select que envía el
 *   formulario al cambiar.
 * - Exportar: indicador mientras se descarga.
 * - Eliminar: confirmación SweetAlert y POST con CSRF.
 * - Formulario: cambios sin guardar (data-dirty), foco al primer error y
 *   aviso SweetAlert; selector de color con vista previa de la insignia.
 * Sin dependencias nuevas: SweetAlert2 lo carga base.html (v11.10.1).
 */
(function () {
  'use strict';

  function hexToRgb(hex) {
    var h = String(hex || '').replace('#', '');
    if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
    return [0, 2, 4].map(function (i) { return parseInt(h.substr(i, 2), 16); });
  }

  function pad2(value) {
    return (value.length < 2 ? '0' : '') + value;
  }

  function rgbToHex(rgb) {
    return '#' + rgb.map(function (v) {
      return pad2(Math.max(0, Math.min(255, Math.round(v))).toString(16));
    }).join('');
  }

  function lumOf(rgb) {
    var f = function (v) {
      v /= 255;
      return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    };
    return 0.2126 * f(rgb[0]) + 0.7152 * f(rgb[1]) + 0.0722 * f(rgb[2]);
  }

  function readable(hex) {
    var rgb = hexToRgb(hex), n = 0;
    while (1.05 / (lumOf(rgb) + 0.05) < 4.5 && n < 24) {
      rgb = rgb.map(function (v) { return v * 0.94; });
      n++;
    }
    return rgbToHex(rgb);
  }

  function mixWhite(hex, p) {
    return rgbToHex(hexToRgb(hex).map(function (v) { return v + (255 - v) * p; }));
  }

  // ---- Búsqueda inteligente (sin botón): envío automático con debounce ----
  // Marca temporal en sessionStorage justo antes de enviar: tras recargar,
  // devuelve el foco al campo con el cursor al final (solo si vino de buscar).
  var qInput = document.getElementById('q');
  function markSearchSubmit() {
    try { sessionStorage.setItem('sgr-search-focus', String(Date.now())); } catch (e) {}
  }
  function submitSearch() {
    var form = qInput ? qInput.form : document.getElementById('toolbarForm');
    if (!form) return;
    markSearchSubmit();
    form.submit();
  }
  if (qInput) {
    var qTimer = null;
    qInput.addEventListener('input', function () {
      if (qTimer) clearTimeout(qTimer);
      qTimer = setTimeout(function () { qTimer = null; submitSearch(); }, 350);
    });
    // La X nativa (evento search) y Enter envían de inmediato y cancelan
    // el temporizador pendiente para no enviar dos veces.
    qInput.addEventListener('search', function () {
      if (qTimer) { clearTimeout(qTimer); qTimer = null; }
      // Si el campo quedó vacío, igual se envía: muestra todos los registros.
      submitSearch();
    });
    qInput.form.addEventListener('submit', function () {
      if (qTimer) { clearTimeout(qTimer); qTimer = null; }
      markSearchSubmit();
    });
    // Tras recargar por buscar: foco al campo con el cursor al final.
    var pending = null;
    try { pending = sessionStorage.getItem('sgr-search-focus'); } catch (e) {}
    if (pending) {
      try { sessionStorage.removeItem('sgr-search-focus'); } catch (e) {}
      qInput.focus();
      var end = qInput.value.length;
      try { qInput.setSelectionRange(end, end); } catch (e) {}
    }
  }

  // ---- Filtro de estado: envía el formulario al cambiar ----
  var estadoSel = document.getElementById('estado');
  if (estadoSel) {
    estadoSel.addEventListener('change', function () {
      var form = document.getElementById('toolbarForm');
      if (form) form.submit();
    });
  }

  // ---- Exportar: indicador de carga mientras se genera el archivo ----
  document.querySelectorAll('.js-export').forEach(function (link) {
    link.addEventListener('click', function () {
      if (link.dataset.busy) return false;
      link.dataset.busy = '1';
      var label = link.querySelector('span');
      if (label) link.dataset.label = label.textContent;
      if (label) label.textContent = 'Generando…';
      link.style.opacity = '0.6';
    });
  });

  // ---- Eliminar: confirmación SweetAlert + POST con CSRF ----
  function csrfToken() {
    var holder = document.getElementById('csrfHolder');
    if (!holder) return '';
    var input = holder.querySelector('input');
    return input ? input.value : '';
  }

  document.querySelectorAll('[data-delete-url]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var url = btn.getAttribute('data-delete-url');
      var label = btn.getAttribute('data-delete-label') || 'registro';
      Swal.fire({
        icon: 'warning',
        title: '¿Eliminar ' + label.toLowerCase() + '?',
        text: 'Se marcará como eliminada y dejará de aparecer en las listas. Esta acción queda registrada en la auditoría.',
        showCancelButton: true,
        confirmButtonText: 'Sí, eliminar',
        cancelButtonText: 'Cancelar',
        confirmButtonColor: '#920000'
      }).then(function (result) {
        if (!result.isConfirmed) return;
        var form = document.createElement('form');
        form.method = 'post';
        form.action = url;
        var token = document.createElement('input');
        token.type = 'hidden';
        token.name = 'csrfmiddlewaretoken';
        token.value = csrfToken();
        form.appendChild(token);
        document.body.appendChild(form);
        form.submit();
      });
    });
  });

  // ---- Formulario: cambios sin guardar, errores y vista previa de color ----
  var form = document.getElementById('crudForm');
  if (form) {
    var cancelBtn = document.getElementById('cancelBtn');

    function setDirty() { form.dataset.dirty = '1'; }
    form.addEventListener('input', setDirty);
    form.addEventListener('change', setDirty);

    // Cancelar pregunta si hay cambios sin guardar (solo crear/editar).
    if (cancelBtn && cancelBtn.tagName === 'A') {
      cancelBtn.addEventListener('click', function (e) {
        if (form.dataset.dirty) {
          e.preventDefault();
          Swal.fire({
            icon: 'question',
            title: '¿Descartar los cambios?',
            text: 'Los datos que escribiste no se guardarán.',
            showCancelButton: true,
            confirmButtonText: 'Descartar',
            cancelButtonText: 'Seguir editando',
            confirmButtonColor: '#920000'
          }).then(function (result) {
            if (result.isConfirmed) window.location.href = cancelBtn.href;
          });
        }
      });
    }

    // Errores del servidor: foco al primer campo marcado + aviso.
    if (form.dataset.hasErrors) {
      var firstInvalid = form.querySelector('[aria-invalid="true"], .err');
      var input = firstInvalid && firstInvalid.closest('div') ?
        firstInvalid.closest('div').querySelector('.in') : null;
      if (input) input.focus();
      else if (firstInvalid) firstInvalid.scrollIntoView({ block: 'center' });
      Swal.fire({
        icon: 'warning',
        title: 'Revisa los campos marcados',
        text: 'Revisa los campos marcados para continuar.',
        confirmButtonColor: '#920000'
      });
    }

    // Selector de color + vista previa de la insignia con degradado.
    var hexInput = document.querySelector('[data-color-input]');
    var picker = document.querySelector('[data-color-picker]');
    var preview = document.querySelector('[data-badge-preview]');
    var previewIcon = document.querySelector('[data-badge-icon]');
    var previewText = document.querySelector('[data-badge-text]');
    var nameInput = document.getElementById('id_name');
    var codeInput = document.getElementById('id_code');

    function validHex(value) {
      return /^#[0-9A-Fa-f]{6}$/.test(String(value || '').trim());
    }

    function refreshPreview() {
      if (!hexInput || !preview) return;
      var hex = hexInput.value.trim();
      if (hex && hex[0] !== '#' && /^[0-9A-Fa-f]{6}$/.test(hex)) hex = '#' + hex;
      if (!validHex(hex)) hex = '#920000';
      var dc = readable(hex), dm = mixWhite(hex, 0.55);
      preview.style.background =
        'linear-gradient(90deg,' + dc + ' 0,' + dc + ' 30px,' + dm + ' 54px,#fff 100%)';
      if (previewIcon) {
        previewIcon.style.background = dc;
        previewIcon.style.color = '#fff';
      }
      if (previewText) {
        var code = (codeInput && codeInput.value.trim()) || '—';
        var name = (nameInput && nameInput.value.trim()) || 'Delegación';
        previewText.textContent = code + ' | Delegación ' + name;
      }
    }

    if (hexInput && picker) {
      hexInput.addEventListener('input', function () {
        if (validHex(hexInput.value.trim())) picker.value = hexInput.value.trim();
        refreshPreview();
      });
      picker.addEventListener('input', function () {
        hexInput.value = picker.value.toUpperCase();
        refreshPreview();
      });
      if (nameInput) nameInput.addEventListener('input', refreshPreview);
      if (codeInput) codeInput.addEventListener('input', refreshPreview);
      refreshPreview();
    }
  }

  // ---- Listado: filas por página y "Limpiar filtros" ----
  // El selector del pie envía su propio formulario al cambiar (el botón
  // sr-only del formulario sigue funcionando sin JavaScript).
  var perPageSel = document.getElementById('per_page');
  if (perPageSel) {
    perPageSel.addEventListener('change', function () {
      var rowsForm = document.getElementById('rowsForm');
      if (rowsForm) rowsForm.submit();
    });
  }

  // Grilla de filtros del módulo: cada select envía el formulario al cambiar
  // (el botón sr-only del formulario sigue funcionando sin JavaScript).
  var filtersForm = document.getElementById('filtersForm');
  if (filtersForm) {
    Array.prototype.forEach.call(
      filtersForm.querySelectorAll('select'),
      function (select) {
        select.addEventListener('change', function () {
          filtersForm.submit();
        });
      }
    );
  }

  // "Limpiar filtros" se ve deshabilitado cuando no hay filtros activos:
  // aria-disabled evita la navegación sin ocultar el control.
  var clearBtn = document.getElementById('clearBtn');
  if (clearBtn) {
    clearBtn.addEventListener('click', function (event) {
      if (clearBtn.getAttribute('aria-disabled') === 'true') event.preventDefault();
    });
  }
})();
