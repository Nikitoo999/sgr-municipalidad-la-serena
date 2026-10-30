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

  // ---- Chat de la delegación (WebSocket) ----
  var chatFab = document.getElementById('chatFab');
  var chatPanel = document.getElementById('chatPanel');
  var chatCloseBtn = document.getElementById('chatCloseBtn');
  var chatForm = document.getElementById('chatForm');
  var chatInput = document.getElementById('chatInput');
  var chatMessages = document.getElementById('chatMessages');
  var delegation = document.body.dataset.delegation || 'ALL';
  var chatSocket = null;

  function wsUrl(path) {
    var proto = location.protocol === 'https:' ? 'wss' : 'ws';
    return proto + '://' + location.host + path;
  }

  function ensureChatSocket() {
    if (chatSocket && (chatSocket.readyState === WebSocket.CONNECTING || chatSocket.readyState === WebSocket.OPEN)) {
      return;
    }
    chatSocket = new WebSocket(wsUrl('/ws/chat/' + encodeURIComponent(delegation) + '/'));
    chatSocket.onmessage = function (e) {
      var data;
      try { data = JSON.parse(e.data); } catch (err) { return; }
      appendChatMessage(data.user, data.message, data.timestamp);
    };
  }

  function appendChatMessage(user, message, timestamp) {
    if (!chatMessages) return;
    var row = document.createElement('div');
    row.className = 'chat-msg';
    var meta = document.createElement('div');
    meta.className = 'chat-meta';
    meta.textContent = (user ? user + ' · ' : '') + (timestamp || '');
    var body = document.createElement('div');
    body.className = 'chat-text';
    body.textContent = message;
    row.appendChild(meta);
    row.appendChild(body);
    chatMessages.appendChild(row);
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  if (chatFab && chatPanel && chatCloseBtn) {
    chatFab.addEventListener('click', function () {
      var opening = chatPanel.hidden;
      chatPanel.hidden = !opening;
      chatFab.setAttribute('aria-expanded', opening ? 'true' : 'false');
      if (opening) ensureChatSocket();
    });
    chatCloseBtn.addEventListener('click', function () {
      chatPanel.hidden = true;
      chatFab.setAttribute('aria-expanded', 'false');
    });
  }

  if (chatForm && chatInput) {
    chatForm.addEventListener('submit', function (e) {
      e.preventDefault();
      var msg = chatInput.value.trim();
      if (!msg) return;
      ensureChatSocket();
      if (chatSocket && chatSocket.readyState === WebSocket.OPEN) {
        chatSocket.send(JSON.stringify({ message: msg }));
        chatInput.value = '';
      }
    });
  }

  // ---- Aviso en vivo de nuevas atenciones (WebSocket) ----
  function escHtml(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function statusBadge(estado) {
    var cls = 'b-off';
    if (estado === 'Ingresada') cls = 'b-info';
    else if (estado === 'En gestión') cls = 'b-warn';
    else if (estado === 'Resuelta') cls = 'b-ok';
    return '<span class="badge ' + cls + '">' + escHtml(estado) + '</span>';
  }

  function delegationChip(code, color) {
    return '<span class="chip" title="' + escHtml(code) + '">' +
      '<svg class="sq" viewBox="0 0 10 10" aria-hidden="true"><rect width="10" height="10" fill="' + escHtml(color || '#920000') + '"/></svg>' +
      escHtml(code) + '</span>';
  }

  function attentionRowHtml(data) {
    var eye = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg>';
    var detailUrl = '/atenciones/' + escHtml(data.id || '') + '/';
    var cells =
      '<td>' + escHtml(data.number) + '</td>' +
      '<td>' + escHtml(data.fecha) + '</td>' +
      '<td>' + escHtml(data.solicitante) + '</td>' +
      '<td>' + escHtml(data.tipo) + '</td>' +
      '<td>' + escHtml(data.subtipo) + '</td>' +
      '<td>' + delegationChip(data.delegation, data.delegation_color) + '</td>' +
      '<td>' + escHtml(data.responsable) + '</td>' +
      '<td>' + statusBadge(data.estado) + '</td>' +
      '<td><div class="acts"><a class="ib v" href="' + detailUrl + '" data-tip="Ver detalle" aria-label="Ver detalle de la atención">' + eye + '</a></div></td>';
    return '<tr>' + cells + '</tr>';
  }

  function prependAttentionRow(data) {
    var tbody = document.querySelector('table tbody');
    if (tbody) {
      tbody.insertAdjacentHTML('afterbegin', attentionRowHtml(data));
    }
  }

  function rowIsVisible(number) {
    var tbody = document.querySelector('table tbody');
    if (!tbody) return false;
    var rows = tbody.querySelectorAll('tr');
    for (var i = 0; i < rows.length; i++) {
      var first = rows[i].querySelector('td');
      if (first && first.textContent.trim() === String(number)) {
        return true;
      }
    }
    return false;
  }

  function refreshLiveList(html) {
    var doc = new DOMParser().parseFromString(html, 'text/html');
    var main = document.querySelector('main');
    if (!main) return;
    var anchor = main.querySelector('#csrfHolder');
    ['.tablewrap', '.pager', '.state'].forEach(function (sel) {
      var current = main.querySelector(sel);
      if (current) current.remove();
    });
    ['.tablewrap', '.pager', '.state'].forEach(function (sel) {
      var fresh = doc.querySelector(sel);
      if (!fresh) return;
      if (anchor) {
        main.insertBefore(fresh, anchor);
      } else {
        main.appendChild(fresh);
      }
    });
  }

  var isAttentionsList = (
    document.body.dataset.module === 'attenciones' ||
    document.body.dataset.module === 'attentions' ||
    window.location.pathname.indexOf('/atenciones') !== -1
  );

  if (isAttentionsList) {
    console.log('[SGR WS] Inicializando WebSocket de atenciones...');
    var wsScheme = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
    var deleg = document.body.dataset.delegation || 'ALL';
    var attWsUrl = wsScheme + window.location.host + '/ws/atenciones/' + deleg + '/';
    console.log('[SGR WS] Conectando a:', attWsUrl);

    var attSocket = new WebSocket(attWsUrl);

    attSocket.onopen = function () {
      console.log('[SGR WS] Conectado exitosamente.');
    };

    attSocket.onerror = function (err) {
      console.error('[SGR WS] Error en WebSocket:', err);
    };

    attSocket.onmessage = function (e) {
      var data;
      try { data = JSON.parse(e.data); } catch (err) { return; }
      console.log('[SGR WS] Evento recibido:', data);
      if (data.type !== 'attention_created') return;

      var isCreated = data.action !== 'updated';
      var toastTitle = isCreated
        ? 'Nueva atención ingresada: ' + (data.number || '')
        : 'Atención actualizada: ' + (data.number || '');

      Swal.fire({
        toast: true,
        position: 'top-end',
        icon: 'info',
        title: toastTitle,
        showConfirmButton: false,
        timer: 6000,
        timerProgressBar: true
      });

      fetch(window.location.href, {
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
        credentials: 'same-origin'
      })
        .then(function (resp) { return resp.text(); })
        .then(function (html) {
          refreshLiveList(html);
          if (isCreated && !rowIsVisible(data.number)) {
            prependAttentionRow(data);
          }
        })
        .catch(function (err) {
          console.error('[SGR WS] Error al refrescar la lista:', err);
        });
    };
  }
})();
