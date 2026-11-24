/**
 * sgr.js — JavaScript ligero del shell (versión actualizada).
 * - Menú móvil, anti-doble-Envío, cambio de delegación, confirmación de salida.
 * - WebSocket Heartbeat + Reconexión con Backoff Exponencial.
 */
(function () {
  'use strict';

  // ==== WebSocket Heartbeat + Reconexión (mejora de producción) ====

  /**
   * Estado global del cliente WebSocket.
   * - connected: boolean — si hay conexión activa.
   * - reconnecting: boolean — si se está intentando reconectar.
   * - attempt: número de intentos de reconectar.
   */
  var wsState = {
    connected: false,
    reconnecting: false,
    attempt: 0,
    maxAttempts: 12,
    reconnectDelay: 1000,
    pingInterval: 25000,
    pongTimeout: 10000,
    reconnectDelayMax: 30000,
  };

  var wsIndicator = null;

  function ensureIndicator() {
    if (wsIndicator) return wsIndicator;
    wsIndicator = document.createElement('div');
    wsIndicator.id = 'wsIndicator';
    wsIndicator.className = 'ws-offline';
    wsIndicator.setAttribute('aria-live', 'polite');
    wsIndicator.setAttribute('role', 'status');
    wsIndicator.textContent = 'Conexión perdida. Reconectando…';
    document.head.appendChild(wsIndicator);
    return wsIndicator;
  }

  function updateWsIndicator(isOnline) {
    var el = ensureIndicator();
    if (isOnline) {
      el.classList.remove('ws-offline');
      el.classList.add('ws-online');
      el.textContent = 'Conexión en vivo.';
    } else {
      el.classList.remove('ws-online');
      el.classList.add('ws-offline');
      el.textContent = 'Conexión perdida. Reconectando…';
    }
  }

  function stopHeartbeat(socket) {
    if (socket.pingTimer) clearInterval(socket.pingTimer);
    if (socket.pongTimer) clearTimeout(socket.pongTimer);
    socket.pingTimer = null;
    socket.pongTimer = null;
  }

  // Sin respuesta al ping: se cierra el socket con un código propio (4000) y
  // onclose programa la reconexión con espera exponencial.
  function onConnectionLost(socket) {
    stopHeartbeat(socket);
    try {
      socket.close(4000, 'heartbeat');
    } catch (err) {
      scheduleReconnect();
    }
  }

  function startHeartbeat(socket) {
    stopHeartbeat(socket);

    function sendPing() {
      if (socket.readyState !== WebSocket.OPEN) return;
      if (socket.pongTimer) return;  // aún esperando la respuesta anterior
      try {
        socket.send(JSON.stringify({ type: 'ping' }));
        socket.pongTimer = setTimeout(function () {
          onConnectionLost(socket);
        }, wsState.pongTimeout);
      } catch (err) {
        onConnectionLost(socket);
      }
    }

    sendPing();
    socket.pingTimer = setInterval(sendPing, wsState.pingInterval);
  }

  function scheduleReconnect() {
    if (wsState.reconnecting) return;
    if (wsState.attempt >= wsState.maxAttempts) {
      updateWsIndicator(false);
      wsState.reconnecting = false;
      console.warn('[SGR WS] Número máximo de intentos alcanzado.');
      return;
    }

    wsState.reconnecting = true;
    var delay = Math.min(
      wsState.reconnectDelay * Math.pow(2, wsState.attempt),
      wsState.reconnectDelayMax
    );
    var nextAttempt = wsState.attempt + 1;

    if (wsState.pingTimer) clearInterval(wsState.pingTimer);
    if (wsState.pongTimer) clearTimeout(wsState.pongTimer);

    updateWsIndicator(false);

    console.log(
      '[SGR WS] Reconectando en ' + delay + 'ms (intento ' + nextAttempt + '/' + wsState.maxAttempts + ')'
    );

    wsState.pingTimer = setTimeout(function () {
      wsState.attempt = nextAttempt;
      connectWebSocket();
    }, delay);
  }

  function connectWebSocket() {
    var wsScheme = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
    var deleg = document.body.dataset.delegation || 'ALL';
    var wsUrl = wsScheme + window.location.host + '/ws/atenciones/' + encodeURIComponent(deleg) + '/';

    var socket = new WebSocket(wsUrl);

    socket.onopen = function () {
      wsState.connected = true;
      wsState.attempt = 0;
      wsState.reconnecting = false;
      console.log('[SGR WS] Conectado exitosamente.');
      updateWsIndicator(true);
      startHeartbeat(socket);
    };

    socket.onmessage = function (e) {
      var data;
      try {
        data = JSON.parse(e.data);
      } catch (err) {
        return;
      }
      if (data && data.type === 'pong') {
        if (socket.pongTimer) clearTimeout(socket.pongTimer);
        socket.pongTimer = null;
        return;
      }
      if (data && data.type === 'attention_created') {
        handleAttentionEvent(data);
      }
    };

    socket.onerror = function (err) {
      console.error('[SGR WS] Error:', err);
    };

    socket.onclose = function (event) {
      stopHeartbeat(socket);
      wsState.connected = false;
      console.log('[SGR WS] Cerrado. code=' + event.code + ' reason=' + event.reason);
      if (event.code === 1008) {
        console.warn('[SGR WS] Política de servidor: conexión denegada (code 1008).');
        updateWsIndicator(false);
        wsState.reconnecting = false;
        return;
      }
      if (event.code === 1000) {
        console.log('[SGR WS] Desconexión normal (1000).');
        updateWsIndicator(false);
        wsState.reconnecting = false;
        return;
      }
      scheduleReconnect();
    };

    socket._sgr = socket._sgr || {};
    socket._sgr.state = wsState;
  }

  function handleAttentionEvent(data) {
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
  }

  var isAttentionsList = (
    document.body.dataset.module === 'attenciones' ||
    document.body.dataset.module === 'attentions' ||
    window.location.pathname.indexOf('/atenciones') !== -1
  );

  if (isAttentionsList) {
    console.log('[SGR WS] Inicializando WebSocket de atenciones...');
    connectWebSocket();
  }

  // ==== Menú móvil ====
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

  // Cambio de delegación activa: si hay un formulario con cambios sin
  // guardar, se pide confirmación (requisito de la segunda evaluación).
  var ctx = document.getElementById('ctxSel');
  if (ctx) {
    var previousCtx = ctx.value;
    ctx.addEventListener('change', function () {
      var form = document.getElementById('ctxForm');
      if (!form) return;
      var dirty = document.querySelector('form[data-dirty="1"]');
      if (!dirty || !window.Swal) { form.submit(); return; }
      Swal.fire({
        icon: 'warning',
        title: '¿Cambiar de delegación?',
        text: 'Hay cambios sin guardar en el formulario: se perderán al cambiar de delegación.',
        showCancelButton: true,
        confirmButtonText: 'Cambiar y descartar',
        cancelButtonText: 'Seguir editando',
        confirmButtonColor: '#920000'
      }).then(function (result) {
        if (result.isConfirmed) {
          form.submit();
        } else {
          ctx.value = previousCtx;
        }
      });
    });
  }

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

  var profileModal = document.getElementById('profileModal');
  var openProfileBtn = document.getElementById('openProfileModalBtn');
  var closeProfileBtn = document.getElementById('closeProfileModalBtn');
  var openModal = function () {
    if (profileModal) profileModal.hidden = false;
  };
  var closeModal = function () {
    if (profileModal) profileModal.hidden = true;
  };
  if (profileModal && openProfileBtn && closeProfileBtn) {
    openProfileBtn.addEventListener('click', openModal);
    closeProfileBtn.addEventListener('click', closeModal);
  }
})();
