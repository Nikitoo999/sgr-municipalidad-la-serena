/*
 * SGR – Ventana emergente (modal) para ingresar registros nuevos.
 *
 * 1. Enlaces con ``data-sgr-modal`` (botones "Nueva delegación", "Nuevo
 *    usuario", "Ingresar atención"...): abren la página del formulario con
 *    ``?modal=1`` dentro de un iframe en una ventana compacta con una X arriba.
 *    La página se muestra sin cabecera ni menú (body.embed, ver portal/modal.py).
 *    Al guardar bien, el servidor responde con portal/modal_done.html, que avisa
 *    por postMessage: el modal se cierra y el listado se recarga (el mensaje de
 *    éxito aparece con SweetAlert2). Si hay errores, se ven dentro del modal.
 * 2. Ventanas ya presentes en la página (``.smodal-backdrop[data-sgr-dialog]``)
 *    se abren con ``data-open-modal="id"`` y se cierran con ``data-close-modal``.
 *
 * Sin JavaScript, los enlaces siguen llevando a la página completa.
 */
(function () {
  'use strict';

  var MSG_TYPE = 'sgr-modal';
  var ICON_X = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
    '<path d="M18 6 6 18M6 6l12 12"/></svg>';

  // ------------------------------------------------------------------
  // Dentro del iframe (página con body.embed)
  // ------------------------------------------------------------------
  if (document.body.classList.contains('embed') && window.parent !== window) {
    var post = function (action, extra) {
      var msg = { type: MSG_TYPE, action: action };
      if (extra) Object.keys(extra).forEach(function (k) { msg[k] = extra[k]; });
      window.parent.postMessage(msg, window.location.origin);
    };
    var reportHeight = function () {
      post('resize', { height: document.documentElement.scrollHeight });
    };
    window.addEventListener('load', reportHeight);
    if (window.ResizeObserver) {
      new ResizeObserver(reportHeight).observe(document.body);
    } else {
      setInterval(reportHeight, 500);
    }
    reportHeight();

    // "Cancelar" cierra el modal (la ventana principal pregunta si hay cambios).
    document.addEventListener('click', function (e) {
      var cancel = e.target.closest && e.target.closest('#cancelBtn');
      if (!cancel) return;
      e.preventDefault();
      e.stopImmediatePropagation();
      post('close');
    }, true);

    var form = document.getElementById('crudForm');
    if (form) {
      var markDirty = function () { post('dirty'); };
      form.addEventListener('input', markDirty, { once: true });
      form.addEventListener('change', markDirty, { once: true });
    }
    // Errores de validación: la ventana principal vuelve a mostrar el inicio.
    if (form && form.dataset.hasErrors) post('errors');
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && !document.querySelector('.swal2-container')) post('close');
    });
    return;
  }

  // ------------------------------------------------------------------
  // Ventana principal
  // ------------------------------------------------------------------
  var current = null;

  function withModalParam(href) {
    var url = new URL(href, window.location.href);
    url.searchParams.set('modal', '1');
    return url.toString();
  }

  function confirmDiscard() {
    if (!window.Swal) return Promise.resolve(window.confirm('¿Descartar los cambios sin guardar?'));
    return Swal.fire({
      icon: 'warning',
      title: '¿Cerrar sin guardar?',
      text: 'Los datos ingresados en el formulario se perderán.',
      showCancelButton: true,
      confirmButtonText: 'Cerrar sin guardar',
      cancelButtonText: 'Seguir editando',
      confirmButtonColor: '#920000'
    }).then(function (r) { return r.isConfirmed; });
  }

  function closeFrameModal(force) {
    if (!current) return;
    var state = current;
    var finish = function () {
      if (current !== state) return;
      state.backdrop.remove();
      document.body.classList.remove('smodal-open');
      current = null;
      if (state.opener && state.opener.focus) state.opener.focus();
    };
    if (!force && state.dirty) {
      confirmDiscard().then(function (ok) { if (ok) finish(); });
    } else {
      finish();
    }
  }

  function openFrameModal(href, title, opener) {
    if (current) closeFrameModal(true);
    var backdrop = document.createElement('div');
    backdrop.className = 'smodal-backdrop';
    var titleId = 'smodal-title-' + Date.now();
    backdrop.innerHTML =
      '<div class="smodal" role="dialog" aria-modal="true" aria-labelledby="' + titleId + '">' +
        '<div class="smodal-head"><h2 id="' + titleId + '"></h2>' +
        '<button type="button" class="smodal-close" aria-label="Cerrar">' + ICON_X + '</button></div>' +
        '<div class="smodal-body"><div class="smodal-loading">Cargando…</div>' +
        '<iframe class="smodal-frame"></iframe></div>' +
      '</div>';
    backdrop.querySelector('h2').textContent = title || 'Nuevo registro';
    var frame = backdrop.querySelector('iframe');
    frame.title = title || 'Formulario';
    var loading = backdrop.querySelector('.smodal-loading');
    frame.addEventListener('load', function () {
      var loadedUrl = '';
      try { loadedUrl = frame.contentWindow.location.href; } catch (err) { return; }
      // El navegador puede disparar "load" con la página vacía inicial: se ignora.
      if (!loadedUrl || loadedUrl === 'about:blank') return;
      loading.hidden = true;
      try {
        // Si la página no quedó en modo modal (p. ej., la sesión expiró y se
        // redirigió al login), se abre esa página a pantalla completa.
        var doc = frame.contentDocument;
        if (doc && doc.body && !doc.body.classList.contains('embed') &&
            !doc.getElementById('sgr-modal-redirect')) {
          window.location.href = loadedUrl.replace(/([?&])modal=1&?/, '$1').replace(/[?&]$/, '');
        }
      } catch (err) { /* otro origen: no debería ocurrir */ }
    });
    // La dirección se asigna antes de insertar el iframe en la página.
    frame.src = withModalParam(href);
    backdrop.querySelector('.smodal-close').addEventListener('click', function () { closeFrameModal(false); });
    document.body.appendChild(backdrop);
    document.body.classList.add('smodal-open');
    current = { backdrop: backdrop, frame: frame, dirty: false, opener: opener };
    backdrop.querySelector('.smodal-close').focus();
  }

  window.addEventListener('message', function (e) {
    if (!current || e.origin !== window.location.origin) return;
    if (e.source !== current.frame.contentWindow) return;
    var data = e.data || {};
    if (data.type !== MSG_TYPE) return;
    switch (data.action) {
      case 'resize':
        if (typeof data.height === 'number') current.frame.style.height = Math.ceil(data.height) + 'px';
        break;
      case 'dirty':
        current.dirty = true;
        break;
      case 'errors':
        current.dirty = true;
        break;
      case 'close':
        closeFrameModal(false);
        break;
      case 'done':
        closeFrameModal(true);
        window.location.reload();
        break;
    }
  });

  document.addEventListener('click', function (e) {
    var link = e.target.closest && e.target.closest('a[data-sgr-modal]');
    if (!link) return;
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    openFrameModal(link.href, link.getAttribute('data-modal-title') || link.textContent.trim(), link);
  });

  // ------------------------------------------------------------------
  // Ventanas en la misma página (data-open-modal / data-close-modal)
  // ------------------------------------------------------------------
  var lastOpener = null;

  function openDialog(dialog, opener) {
    dialog.hidden = false;
    document.body.classList.add('smodal-open');
    lastOpener = opener || null;
    var first = dialog.querySelector('input:not([type=hidden]),select,textarea,button');
    if (first) first.focus();
  }

  function closeDialog(dialog) {
    dialog.hidden = true;
    if (!document.querySelector('.smodal-backdrop:not([hidden])')) {
      document.body.classList.remove('smodal-open');
    }
    if (lastOpener && lastOpener.focus) lastOpener.focus();
  }

  document.addEventListener('click', function (e) {
    var opener = e.target.closest && e.target.closest('[data-open-modal]');
    if (opener) {
      var dialog = document.getElementById(opener.getAttribute('data-open-modal'));
      if (dialog) {
        e.preventDefault();
        openDialog(dialog, opener);
      }
      return;
    }
    var closer = e.target.closest && e.target.closest('[data-close-modal]');
    if (closer) {
      var parent = closer.closest('.smodal-backdrop');
      if (parent) {
        e.preventDefault();
        closeDialog(parent);
      }
    }
  });

  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape' || document.querySelector('.swal2-container')) return;
    if (current) {
      closeFrameModal(false);
      return;
    }
    var open = document.querySelector('.smodal-backdrop[data-sgr-dialog]:not([hidden])');
    if (open) closeDialog(open);
  });

  window.SGRModal = { open: openDialog, close: closeDialog, openFrame: openFrameModal };

  // Ventanas que deben abrirse al cargar (p. ej., tras un error de validación).
  var auto = document.querySelector('.smodal-backdrop[data-sgr-dialog][data-open-on-load]');
  if (auto) openDialog(auto);
})();
