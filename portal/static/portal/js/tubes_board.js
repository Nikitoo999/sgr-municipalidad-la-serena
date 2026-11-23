/*
 * SGR – Tablero del tubo (4 columnas: Ingresados, Pendientes, En proceso, Realizados).
 *
 * - Arrastrar una tarjeta a otra columna (o usar su botón de avance) cambia el
 *   estatus por POST (fetch) a ``tube_status``; el servidor valida alcance y
 *   permisos y responde JSON.
 * - Pasar a «Realizados» abre la ventana de cierre: exige foto y código de
 *   verificación (``tube_close``), igual que la planilla.
 */
(function () {
  'use strict';

  var board = document.getElementById('tubeBoard');
  if (!board || !board.dataset.canEdit) return;

  var NEXT = {
    received: ['pending', 'A Pendiente'],
    pending: ['in_progress', 'A Proceso'],
    in_progress: ['done', 'Realizar']
  };
  var csrfInput = document.querySelector('input[name="csrfmiddlewaretoken"]');
  var csrf = csrfInput ? csrfInput.value : '';
  var dragged = null;

  function column(status) { return board.querySelector('.tb-col[data-status="' + status + '"]'); }
  function cardStatus(card) { return card.closest('.tb-col').dataset.status; }

  function toast(icon, text) {
    if (!window.Swal) return;
    Swal.fire({ toast: true, position: 'top-end', timer: 2600, showConfirmButton: false, icon: icon, title: text });
  }

  function bump(el, delta) {
    if (!el) return;
    var n = parseInt(el.textContent, 10) || 0;
    el.textContent = Math.max(0, n + delta);
  }

  function refreshEmpty(col) {
    var cards = col.querySelector('.tb-cards');
    var empty = cards.querySelector('[data-empty]');
    var has = cards.querySelector('.tb-card');
    if (has && empty) empty.remove();
    if (!has && !empty) {
      var p = document.createElement('p');
      p.className = 'tb-empty';
      p.setAttribute('data-empty', '');
      p.textContent = 'Sin solicitudes';
      cards.appendChild(p);
    }
  }

  function updateNextButton(card, status) {
    var btn = card.querySelector('.tb-next');
    var next = NEXT[status];
    if (!btn || !next) return;
    btn.dataset.move = next[0];
    btn.textContent = next[1];
    btn.classList.toggle('do', next[0] === 'done');
  }

  function placeCard(card, from, to) {
    var target = column(to);
    var origin = column(from);
    target.querySelector('.tb-cards').prepend(card);
    bump(origin.querySelector('[data-count]'), -1);
    bump(target.querySelector('[data-count]'), 1);
    bump(document.querySelector('[data-kpi="' + from + '"]'), -1);
    bump(document.querySelector('[data-kpi="' + to + '"]'), 1);
    refreshEmpty(origin);
    refreshEmpty(target);
    updateNextButton(card, to);
  }

  function openClose(card) {
    var dialog = document.getElementById('tubeCloseModal');
    var form = document.getElementById('tubeCloseForm');
    if (!dialog || !form || !window.SGRModal) return;
    form.action = card.dataset.closeUrl;
    form.reset();
    var title = card.querySelector('h3');
    document.getElementById('tubeCloseInfo').textContent =
      card.dataset.code + ' · ' + (title ? title.textContent.trim() : '');
    window.SGRModal.open(dialog, card.querySelector('.tb-next') || card);
  }

  function move(card, to) {
    var from = cardStatus(card);
    if (!to || to === from || !column(to)) return;
    if (to === 'done') {
      openClose(card);
      return;
    }
    var body = new URLSearchParams();
    body.set('status', to);
    card.setAttribute('aria-busy', 'true');
    fetch(card.dataset.statusUrl, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'X-CSRFToken': csrf,
        'X-Requested-With': 'XMLHttpRequest',
        'Content-Type': 'application/x-www-form-urlencoded'
      },
      body: body.toString()
    }).then(function (resp) {
      return resp.json().catch(function () { return { ok: false, message: 'Respuesta inesperada del servidor.' }; });
    }).then(function (data) {
      card.removeAttribute('aria-busy');
      if (data.ok) {
        placeCard(card, from, to);
        toast('success', data.message);
      } else {
        toast('error', data.message || 'No se pudo cambiar el estatus.');
      }
    }).catch(function () {
      card.removeAttribute('aria-busy');
      toast('error', 'Sin conexión con el servidor. Intenta de nuevo.');
    });
  }

  // Botón de avance de cada tarjeta (también sirve con teclado y en pantallas táctiles).
  board.addEventListener('click', function (e) {
    var btn = e.target.closest('.tb-next');
    if (!btn) return;
    move(btn.closest('.tb-card'), btn.dataset.move);
  });

  // Arrastrar y soltar.
  board.addEventListener('dragstart', function (e) {
    var card = e.target.closest('.tb-card[draggable="true"]');
    if (!card) return;
    dragged = card;
    card.classList.add('dragging');
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', card.dataset.id);
  });
  board.addEventListener('dragend', function () {
    if (dragged) dragged.classList.remove('dragging');
    dragged = null;
    board.querySelectorAll('.drop-ok').forEach(function (c) { c.classList.remove('drop-ok'); });
  });
  board.querySelectorAll('.tb-col').forEach(function (col) {
    col.addEventListener('dragover', function (e) {
      if (!dragged || cardStatus(dragged) === col.dataset.status) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      col.classList.add('drop-ok');
    });
    col.addEventListener('dragleave', function (e) {
      if (!col.contains(e.relatedTarget)) col.classList.remove('drop-ok');
    });
    col.addEventListener('drop', function (e) {
      e.preventDefault();
      col.classList.remove('drop-ok');
      if (dragged) move(dragged, col.dataset.status);
    });
  });
})();
