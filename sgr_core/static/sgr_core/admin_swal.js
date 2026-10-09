/* SweetAlert2 en el Django Admin del SGR:
 *  1) Errores de validación de formularios -> modal con la lista de errores.
 *  2) Mensajes de Django (guardado, acciones) -> toast / modal.
 *  3) Confirmación antes de ejecutar acciones masivas.
 */
(function () {
  "use strict";
 
  document.addEventListener("DOMContentLoaded", function () {
    if (typeof Swal === "undefined") {
      return; // si el CDN no cargó, el admin sigue funcionando normal
    }
 
    var queue = [];
 
    // 1) Errores de validación (usa textContent: nunca inserta HTML)
    var errorLists = document.querySelectorAll("ul.errorlist");
    if (errorLists.length) {
      var ul = document.createElement("ul");
      ul.style.textAlign = "left";
      errorLists.forEach(function (list) {
        var row = list.closest(".form-row");
        var labelEl = row ? row.querySelector("label") : null;
        var label = labelEl ? labelEl.textContent.replace(/:\s*$/, "") : "";
        list.querySelectorAll("li").forEach(function (li) {
          var item = document.createElement("li");
          item.textContent = (label ? label + ": " : "") + li.textContent;
          ul.appendChild(item);
        });
      });
      queue.push({
        icon: "error",
        title: "Revisa el formulario",
        html: ul,
        confirmButtonText: "Entendido",
      });
    }
 
    // 2) Mensajes de Django
    var messageList = document.querySelector("ul.messagelist");
    if (messageList) {
      var important = [];
      var soft = [];
      messageList.querySelectorAll("li").forEach(function (li) {
        var text = li.textContent.trim();
        if (li.classList.contains("error") || li.classList.contains("warning")) {
          important.push(text);
        } else {
          soft.push(text);
        }
      });
      messageList.style.display = "none";
      if (important.length) {
        var ul2 = document.createElement("ul");
        ul2.style.textAlign = "left";
        important.forEach(function (t) {
          var li = document.createElement("li");
          li.textContent = t;
          ul2.appendChild(li);
        });
        queue.push({ icon: "warning", title: "Atención", html: ul2, confirmButtonText: "Entendido" });
      }
      if (soft.length) {
        queue.push({
          toast: true,
          position: "top-end",
          icon: "success",
          title: soft.join(" · "),
          showConfirmButton: false,
          timer: 4000,
          timerProgressBar: true,
        });
      }
    }
 
    // Se muestran en orden, una después de otra
    queue.reduce(function (p, opts) {
      return p.then(function () { return Swal.fire(opts); });
    }, Promise.resolve());
 
    // 3) Confirmación de acciones masivas en la lista
    var form = document.getElementById("changelist-form");
    if (form) {
      form.addEventListener("submit", function (e) {
        var select = form.querySelector("select[name='action']");
        if (!select || !select.value) { return; }
        // export no modifica datos; delete_selected ya tiene su propia página de confirmación
        if (select.value === "export_to_excel" || select.value === "delete_selected") { return; }
 
        var across = form.querySelector("input.select-across");
        var selectAll = across && across.value === "1";
        var count = form.querySelectorAll("input.action-select:checked").length;
        if (!count && !selectAll) { return; } // Django mostrará su aviso "no seleccionaste nada"
 
        e.preventDefault();
        var label = select.options[select.selectedIndex].text;
        Swal.fire({
          icon: "question",
          title: "¿Confirmas la acción?",
          text: label + " — " + (selectAll ? "todos los registros del filtro" : count + " registro(s)"),
          showCancelButton: true,
          confirmButtonText: "Sí, ejecutar",
          cancelButtonText: "Cancelar",
        }).then(function (r) {
          if (r.isConfirmed) { form.submit(); }
        });
      });
    }
  });
})();
 