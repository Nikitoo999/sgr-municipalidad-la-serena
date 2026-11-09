/**
 * attention.js — Formulario de atención (Parte 7, Bloque 2B).
 * - Búsqueda de vecino registrado contra /atenciones/solicitantes/?q= (máx.
 *   10): al elegirlo completa RUT, nombre y teléfono (obligatorios; si el
 *   vecino no existe se escriben a mano y se registra al guardar).
 * - RUT con formato 12.345.678-5 al salir del campo (el servidor lo valida).
 * - Sub atención dependiente del tipo (se limpia al cambiar el tipo).
 * - Contador en vivo de la descripción (500 caracteres).
 * - "Motivo de baja" visible solo con el estado "Sin resolver".
 * Sin dependencias nuevas: SweetAlert2 lo carga base.html; crud.js cubre el
 * aviso de cambios sin guardar, el foco al primer error y la confirmación.
 */
(function () {
  'use strict';

  // ---- RUT con puntos y guion (solo ayuda visual) ----
  function formatRut(value) {
    var clean = String(value || '').replace(/[^0-9kK]/g, '').toUpperCase();
    if (clean.length < 2) return value;
    var body = clean.slice(0, -1).replace(/^0+/, '');
    var dv = clean.slice(-1);
    if (!/^\d+$/.test(body)) return value;
    return body.replace(/\B(?=(\d{3})+(?!\d))/g, '.') + '-' + dv;
  }
  var rutInput = document.getElementById('id_neighbor_rut');
  var nameInput = document.getElementById('id_neighbor_name');
  var phoneInput = document.getElementById('id_neighbor_phone');
  if (rutInput) {
    rutInput.addEventListener('blur', function () {
      if (rutInput.value.trim()) rutInput.value = formatRut(rutInput.value.trim());
    });
  }

  // ---- Búsqueda de vecino registrado (solo al crear) ----
  var sol = document.getElementById('f_sol');
  var resultsBox = document.getElementById('f_sol_results');
  if (sol && resultsBox && sol.disabled === false && rutInput) {
    var timer = null;
    var abort = null;

    function clearResults() {
      resultsBox.innerHTML = '';
      resultsBox.hidden = true;
    }

    function renderResults(items) {
      resultsBox.innerHTML = '';
      if (!items.length) {
        var empty = document.createElement('div');
        empty.className = 'nb-empty';
        empty.textContent = 'Sin resultados: ingresa los datos del vecino en los campos de abajo.';
        resultsBox.appendChild(empty);
        resultsBox.hidden = false;
        return;
      }
      var list = document.createElement('div');
      list.className = 'nb-list';
      items.forEach(function (item) {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'nb-item';
        btn.textContent = item.label;
        btn.addEventListener('click', function () {
          rutInput.value = item.rut || '';
          if (nameInput) nameInput.value = item.name || '';
          if (phoneInput) phoneInput.value = item.phone || '';
          sol.value = item.label;
          clearResults();
          // Marca el formulario con cambios (aviso al cancelar) y deja el
          // foco en el teléfono para confirmarlo o corregirlo.
          var form = document.getElementById('crudForm');
          if (form) form.dataset.dirty = '1';
          if (phoneInput) phoneInput.focus();
        });
        list.appendChild(btn);
      });
      resultsBox.appendChild(list);
      resultsBox.hidden = false;
    }

    sol.addEventListener('input', function () {
      if (timer) clearTimeout(timer);
      var q = sol.value.trim();
      if (!q) { clearResults(); return; }
      timer = setTimeout(function () {
        if (abort) abort.abort();
        var xhr = new XMLHttpRequest();
        xhr.open('GET', '/atenciones/solicitantes/?q=' + encodeURIComponent(q));
        xhr.setRequestHeader('Accept', 'application/json');
        xhr.onload = function () {
          if (xhr.status !== 200) return;
          var data = JSON.parse(xhr.responseText);
          renderResults(data.results || []);
        };
        abort = xhr;
        xhr.send();
      }, 250);
    });

    document.addEventListener('click', function (e) {
      if (!resultsBox.contains(e.target) && e.target !== sol) clearResults();
    });
  }

  // ---- Sub atención dependiente del tipo ----
  var typeSel = document.getElementById('id_attention_type');
  var subSel = document.getElementById('id_attention_subtype');
  var subHelp = document.getElementById('f_sub_h');
  var mapNode = document.getElementById('subtype-type-map');
  var subtypeTypeMap = {};
  try { subtypeTypeMap = JSON.parse(mapNode.textContent || '{}'); } catch (e) { subtypeTypeMap = {}; }

  if (typeSel && subSel) {
    var subOptions = Array.prototype.slice.call(subSel.options);
    // En la consulta el servidor deja ambos selectores deshabilitados: el
    // script no debe volver a habilitar la sub atención.
    var readOnly = typeSel.disabled;

    function refreshSub(keepValue) {
      var typeValue = typeSel.value;
      var selected = keepValue || '';
      var allowed = [];
      subOptions.forEach(function (opt) {
        var matches = opt.value && String(subtypeTypeMap[opt.value] || '') === String(typeValue);
        opt.disabled = !opt.value || !matches;
        opt.hidden = !opt.value || !matches;
        if (matches && opt.value) allowed.push(opt.value);
      });
      if (readOnly) {
        subSel.disabled = true;
      } else if (!typeValue) {
        subSel.disabled = true;
        if (subHelp) subHelp.textContent = 'Las opciones dependen del tipo de atención.';
      } else {
        subSel.disabled = false;
        if (subHelp) subHelp.textContent = '';
      }
      if (selected && allowed.indexOf(selected) !== -1) {
        subSel.value = selected;
      } else {
        subSel.value = '';
      }
    }

    refreshSub(subSel.value);

    typeSel.addEventListener('change', function () {
      refreshSub('');  // al cambiar el tipo se limpia la sub atención
    });
  }

  // ---- Motivo de baja: solo con el estado "Sin resolver" ----
  var statusSel = document.getElementById('id_status');
  var unresolvedBox = document.getElementById('unresolvedBox');
  if (statusSel && unresolvedBox) {
    var unresolvedValue = unresolvedBox.getAttribute('data-unresolved-value') || 'unresolved';
    var hasError = !!unresolvedBox.querySelector('.err');
    function toggleReason() {
      unresolvedBox.hidden = statusSel.value !== unresolvedValue && !hasError;
      hasError = false;
    }
    statusSel.addEventListener('change', toggleReason);
    toggleReason();
  }

  // ---- Contador en vivo de la descripción ----
  var desc = document.getElementById('id_description');
  var counter = document.getElementById('f_desc_c');
  if (desc && counter) {
    function count() {
      counter.textContent = desc.value.length + ' de 500 caracteres';
    }
    desc.addEventListener('input', count);
    count();
  }
})();

/**
 * Archivos de la atencion (Clase 9): vista previa de la imagen elegida y
 * aviso inmediato si el archivo supera el peso maximo. Es solo ayuda visual:
 * el servidor vuelve a validar tamano y formato.
 */
(function () {
  'use strict';

  var MB = 1024 * 1024;

  function warn(text) {
    if (window.Swal) {
      Swal.fire({ icon: 'warning', title: 'Archivo no válido', text: text, confirmButtonColor: '#920000' });
    } else {
      window.alert(text);
    }
  }

  function bind(input, maxMb, extensions, onValid) {
    if (!input) return;
    input.addEventListener('change', function () {
      var file = input.files && input.files[0];
      if (!file) { onValid(null); return; }
      var name = file.name.toLowerCase();
      var okExt = extensions.some(function (ext) { return name.slice(-ext.length) === ext; });
      if (!okExt) {
        input.value = '';
        onValid(null);
        warn('Formato no permitido. Usa: ' + extensions.join(', ') + '.');
        return;
      }
      if (file.size > maxMb * MB) {
        input.value = '';
        onValid(null);
        warn('El archivo supera el máximo de ' + maxMb + ' MB.');
        return;
      }
      onValid(file);
    });
  }

  var preview = document.getElementById('evidencePreview');
  var previewBox = document.getElementById('evidencePreviewBox');
  var currentUrl = null;

  bind(document.getElementById('id_evidence_image'), 2, ['.jpg', '.jpeg', '.png', '.webp'], function (file) {
    if (currentUrl) { URL.revokeObjectURL(currentUrl); currentUrl = null; }
    if (!preview || !previewBox) return;
    if (!file) { previewBox.hidden = true; preview.removeAttribute('src'); return; }
    currentUrl = URL.createObjectURL(file);
    preview.src = currentUrl;
    previewBox.hidden = false;
  });

  bind(document.getElementById('id_attachment'), 5, ['.pdf', '.jpg', '.jpeg', '.png', '.webp'], function () {});
})();
