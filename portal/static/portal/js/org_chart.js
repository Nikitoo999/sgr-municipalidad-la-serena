/**
 * Organigrama de organizaciones: filtro de cargos y confirmaciones.
 *
 * - Filtra los nodos por texto (cargo, nombre, RUT, teléfono) y por estado
 *   (cubiertos / vacantes); oculta los niveles que quedan sin nodos visibles.
 * - Abre un solo formulario de edición a la vez.
 * - Pide confirmación (SweetAlert si está disponible) antes de dejar vacante un
 *   cargo o eliminar un cargo del catálogo.
 */
(function () {
  'use strict';

  function normalize(text) {
    return String(text || '')
      .toLowerCase()
      .normalize('NFD')
      .replace(/[̀-ͯ]/g, '')
      .trim();
  }

  var tree = document.getElementById('ocTree');
  var search = document.getElementById('ocSearch');
  var stateSel = document.getElementById('ocState');
  var noResults = document.getElementById('ocNoResults');

  function applyFilter() {
    if (!tree) return;
    var term = normalize(search ? search.value : '');
    var state = stateSel ? stateSel.value : '';
    var visibles = 0;
    tree.querySelectorAll('[data-oc-level]').forEach(function (level) {
      var enNivel = 0;
      level.querySelectorAll('[data-oc-node]').forEach(function (node) {
        var okText = !term || normalize(node.dataset.search).indexOf(term) !== -1;
        var okState = !state || node.dataset.state === state;
        var show = okText && okState;
        node.hidden = !show;
        if (show) enNivel += 1;
      });
      level.hidden = enNivel === 0;
      visibles += enNivel;
    });
    if (noResults) noResults.hidden = visibles !== 0;
  }

  if (search) search.addEventListener('input', applyFilter);
  if (stateSel) stateSel.addEventListener('change', applyFilter);

  // Un solo formulario de asignación/edición abierto a la vez.
  var details = document.querySelectorAll('[data-oc-details]');
  details.forEach(function (d) {
    d.addEventListener('toggle', function () {
      if (!d.open) return;
      details.forEach(function (other) {
        if (other !== d) other.open = false;
      });
      var first = d.querySelector('input:not([type="hidden"])');
      if (first) first.focus();
    });
  });

  // Confirmación antes de acciones que quitan datos.
  document.querySelectorAll('form[data-oc-confirm]').forEach(function (form) {
    form.addEventListener('submit', function (e) {
      if (form.dataset.ocConfirmed === '1') return;
      e.preventDefault();
      var title = form.dataset.ocConfirmTitle || '¿Confirmas la acción?';
      var text = form.dataset.ocConfirm || '';
      var button = form.dataset.ocConfirmButton || 'Confirmar';
      var proceed = function () {
        form.dataset.ocConfirmed = '1';
        form.submit();
      };
      if (window.Swal) {
        window.Swal.fire({
          icon: 'warning',
          title: title,
          text: text,
          showCancelButton: true,
          confirmButtonText: button,
          cancelButtonText: 'Cancelar',
          confirmButtonColor: '#920000',
          focusCancel: true
        }).then(function (result) {
          if (result.isConfirmed) proceed();
        });
      } else if (window.confirm(title + '\n\n' + text)) {
        proceed();
      }
    });
  });
})();
