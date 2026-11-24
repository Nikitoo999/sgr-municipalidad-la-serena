/*
 * SGR – Ingreso de atención (Unidad 3).
 *
 * - "¿Cómo acude la persona?": persona natural o directivo de organización.
 *   Con directivo se busca la organización y se elige un integrante de su
 *   organigrama, que completa RUT, nombre, teléfono y cargo directivo.
 * - Funcionario como civil: al ingresar el RUT se consulta si pertenece a un
 *   funcionario; si es así se pide indicar si acude como civil o si es una
 *   gestión interna. Nunca se bloquea el ingreso.
 * - Ítem de la matriz: al elegir la sub atención se propone su ítem sugerido
 *   si el cargo del responsable lo mide.
 *
 * Todo es ayuda de interfaz: el servidor valida cada dato al guardar.
 */
(function () {
  'use strict';

  function $(id) { return document.getElementById(id); }
  function getJSON(url, done) {
    var xhr = new XMLHttpRequest();
    xhr.open('GET', url);
    xhr.setRequestHeader('Accept', 'application/json');
    xhr.onload = function () {
      if (xhr.status !== 200) return;
      try { done(JSON.parse(xhr.responseText)); } catch (e) { /* respuesta inválida */ }
    };
    xhr.send();
    return xhr;
  }
  function markDirty() {
    var form = $('crudForm');
    if (form) form.dataset.dirty = '1';
  }

  var rutInput = $('id_neighbor_rut');
  var nameInput = $('id_neighbor_name');
  var phoneInput = $('id_neighbor_phone');

  // ---------------- Persona natural / Directivo ----------------
  var directiveBox = $('directiveBox');
  var modeRadios = document.querySelectorAll('input[name="requester_mode"]');
  var orgHidden = $('id_organization');
  var orgInput = $('f_org');
  var orgResults = $('f_org_results');
  var memberSel = $('id_organization_member');
  var roleSel = $('id_directive_role');

  function currentMode() {
    var checked = document.querySelector('input[name="requester_mode"]:checked');
    return checked ? checked.value : 'person';
  }

  function toggleMode() {
    if (!directiveBox) return;
    var isDirective = currentMode() === 'directive';
    directiveBox.hidden = !isDirective;
  }
  Array.prototype.forEach.call(modeRadios, function (radio) {
    radio.addEventListener('change', function () { toggleMode(); markDirty(); });
  });
  toggleMode();

  function fillMembers(orgPk, keepValue) {
    if (!memberSel) return;
    var previous = keepValue || memberSel.value;
    memberSel.innerHTML = '';
    var manual = document.createElement('option');
    manual.value = '';
    manual.textContent = '-- Ingreso manual del directivo --';
    memberSel.appendChild(manual);
    if (!orgPk) return;
    getJSON('/organizaciones/' + encodeURIComponent(orgPk) + '/directiva.json', function (data) {
      (data.members || []).forEach(function (m) {
        var opt = document.createElement('option');
        opt.value = m.pk;
        opt.textContent = m.role + ': ' + m.name;
        opt.dataset.rut = m.rut || '';
        opt.dataset.name = m.name || '';
        opt.dataset.phone = m.phone || '';
        opt.dataset.role = m.role_id || '';
        memberSel.appendChild(opt);
      });
      if (previous) memberSel.value = previous;
    });
  }

  if (orgInput && orgResults && orgHidden) {
    var orgTimer = null;
    var orgXhr = null;
    var clearOrgResults = function () { orgResults.innerHTML = ''; orgResults.hidden = true; };
    orgInput.addEventListener('input', function () {
      orgHidden.value = '';
      fillMembers('');
      if (orgTimer) clearTimeout(orgTimer);
      var q = orgInput.value.trim();
      if (q.length < 2) { clearOrgResults(); return; }
      orgTimer = setTimeout(function () {
        if (orgXhr) orgXhr.abort();
        orgXhr = getJSON('/organizaciones/buscar/?q=' + encodeURIComponent(q), function (data) {
          orgResults.innerHTML = '';
          var items = data.results || [];
          if (!items.length) {
            var empty = document.createElement('div');
            empty.className = 'nb-empty';
            empty.textContent = 'Sin resultados en la base de organizaciones de tu delegación.';
            orgResults.appendChild(empty);
          }
          var list = document.createElement('div');
          list.className = 'nb-list';
          items.forEach(function (item) {
            var btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'nb-item';
            btn.textContent = item.label + (item.detail ? ' · ' + item.detail : '');
            btn.addEventListener('click', function () {
              orgHidden.value = item.pk;
              orgInput.value = item.label;
              clearOrgResults();
              fillMembers(item.pk);
              markDirty();
            });
            list.appendChild(btn);
          });
          orgResults.appendChild(list);
          orgResults.hidden = false;
        });
      }, 250);
    });
    document.addEventListener('click', function (e) {
      if (!orgResults.contains(e.target) && e.target !== orgInput) clearOrgResults();
    });
    // Tras un error de validación, recarga los integrantes de la organización elegida.
    if (orgHidden.value) fillMembers(orgHidden.value, memberSel ? memberSel.getAttribute('data-selected') : '');
  }

  if (memberSel) {
    memberSel.addEventListener('change', function () {
      var opt = memberSel.options[memberSel.selectedIndex];
      if (!opt || !opt.value) return;
      if (rutInput && opt.dataset.rut) rutInput.value = opt.dataset.rut;
      if (nameInput && opt.dataset.name) nameInput.value = opt.dataset.name;
      if (phoneInput && opt.dataset.phone) phoneInput.value = opt.dataset.phone;
      if (roleSel && opt.dataset.role) roleSel.value = opt.dataset.role;
      markDirty();
      checkRut();
    });
  }

  // ---------------- Funcionario como civil ----------------
  var employeeBox = $('employeeBox');
  var employeeText = $('employeeBoxText');
  var selfHelp = $('employeeSelfHelp');
  var lastRut = '';
  var rutXhr = null;

  function hideEmployeeBox() {
    if (!employeeBox) return;
    employeeBox.hidden = true;
    Array.prototype.forEach.call(
      employeeBox.querySelectorAll('input[type="radio"]'),
      function (r) { r.checked = false; }
    );
  }

  function checkRut() {
    if (!rutInput || !employeeBox) return;
    var rut = rutInput.value.trim();
    if (rut === lastRut) return;
    lastRut = rut;
    if (rut.replace(/[^0-9kK]/g, '').length < 7) { hideEmployeeBox(); return; }
    if (rutXhr) rutXhr.abort();
    rutXhr = getJSON('/atenciones/funcionario-por-rut/?rut=' + encodeURIComponent(rut), function (data) {
      var emp = data.employee;
      if (!emp) { hideEmployeeBox(); return; }
      employeeText.textContent = 'Este RUT corresponde a un funcionario municipal: ' + emp.name +
        ' (' + emp.position + ', ' + emp.delegation + '). Indica cómo se registra la solicitud:';
      if (selfHelp) selfHelp.hidden = !emp.is_self;
      employeeBox.hidden = false;
    });
  }

  if (rutInput) {
    // Si el servidor ya mostró el aviso (error de validación), no se repite la consulta.
    if (employeeBox && !employeeBox.hidden) lastRut = rutInput.value.trim();
    rutInput.addEventListener('blur', function () { setTimeout(checkRut, 0); });
    rutInput.addEventListener('change', checkRut);
    // Al elegir un vecino del buscador, el RUT se completa por código.
    document.addEventListener('click', function (e) {
      if (e.target.closest && e.target.closest('#f_sol_results .nb-item')) setTimeout(checkRut, 0);
    });
  }

  // ---------------- Ítem sugerido por la sub atención ----------------
  var subSel = $('id_attention_subtype');
  var itemSel = $('id_item');
  var mapNode = $('subtype-item-map');
  var subtypeItem = {};
  try { subtypeItem = JSON.parse((mapNode && mapNode.textContent) || '{}'); } catch (e) { subtypeItem = {}; }
  if (subSel && itemSel && itemSel.tagName === 'SELECT' && !itemSel.disabled) {
    var autoSet = false;
    subSel.addEventListener('change', function () {
      var suggested = subtypeItem[subSel.value];
      if (!suggested) return;
      var exists = Array.prototype.some.call(itemSel.options, function (o) { return o.value === String(suggested); });
      if (exists && (!itemSel.value || autoSet)) {
        itemSel.value = String(suggested);
        autoSet = true;
      }
    });
    itemSel.addEventListener('change', function () { autoSet = false; });
  }
})();
