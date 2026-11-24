/*
 * SGR – Selector de organización comunitaria (búsqueda en la base JJVV).
 *
 * Marcado: un contenedor [data-org-picker] con un input de texto
 * [data-org-search], un input oculto [data-org-id] y una caja de resultados
 * [data-org-results]. Al elegir, se completa el id y, si el campo
 * "Solicitante" está vacío, se usa el nombre de la organización.
 * El servidor valida la organización al guardar.
 */
(function () {
  'use strict';

  document.querySelectorAll('[data-org-picker]').forEach(function (box) {
    var input = box.querySelector('[data-org-search]');
    var hidden = box.querySelector('[data-org-id]');
    var results = box.querySelector('[data-org-results]');
    if (!input || !hidden || !results) return;
    var timer = null;
    var xhr = null;

    function clear() { results.innerHTML = ''; results.hidden = true; }

    input.addEventListener('input', function () {
      hidden.value = '';
      if (timer) clearTimeout(timer);
      var q = input.value.trim();
      if (q.length < 2) { clear(); return; }
      timer = setTimeout(function () {
        if (xhr) xhr.abort();
        xhr = new XMLHttpRequest();
        xhr.open('GET', '/organizaciones/buscar/?q=' + encodeURIComponent(q));
        xhr.setRequestHeader('Accept', 'application/json');
        xhr.onload = function () {
          if (xhr.status !== 200) return;
          var data;
          try { data = JSON.parse(xhr.responseText); } catch (e) { return; }
          results.innerHTML = '';
          var list = document.createElement('div');
          list.className = 'nb-list';
          (data.results || []).forEach(function (item) {
            var btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'nb-item';
            btn.textContent = item.label + (item.detail ? ' · ' + item.detail : '');
            btn.addEventListener('click', function () {
              hidden.value = item.pk;
              input.value = item.label;
              var form = input.form;
              var requester = form ? form.querySelector('[name="requester"]') : null;
              if (requester && !requester.value.trim()) requester.value = item.label;
              clear();
            });
            list.appendChild(btn);
          });
          if (!list.children.length) {
            var empty = document.createElement('div');
            empty.className = 'nb-empty';
            empty.textContent = 'Sin resultados en la base de organizaciones.';
            results.appendChild(empty);
          } else {
            results.appendChild(list);
          }
          results.hidden = false;
        };
        xhr.send();
      }, 250);
    });
    document.addEventListener('click', function (e) {
      if (!box.contains(e.target)) clear();
    });
  });
})();
