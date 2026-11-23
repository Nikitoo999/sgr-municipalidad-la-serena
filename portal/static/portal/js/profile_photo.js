/*
 * SGR – Foto de perfil con encuadre (preview "Mi Perfil y Ajuste de Foto").
 *
 * Al elegir una imagen se muestra un círculo donde se arrastra y se ajusta el
 * zoom; al guardar se envía un recorte cuadrado de 400×400 en JPEG. Sin
 * JavaScript se envía la imagen original. El servidor valida tamaño y formato.
 */
(function () {
  'use strict';

  var form = document.getElementById('photoForm');
  var input = document.getElementById('pf_photo');
  var cropBox = document.getElementById('photoCrop');
  var canvas = document.getElementById('photoCanvas');
  var zoom = document.getElementById('pf_zoom');
  if (!form || !input || !canvas || !zoom || !window.FileReader) return;

  var ctx = canvas.getContext('2d');
  var img = null;
  var offset = { x: 0, y: 0 };
  var drag = null;
  var SIZE = canvas.width;
  var OUT = 400;

  function baseScale() {
    return img ? Math.max(SIZE / img.width, SIZE / img.height) : 1;
  }

  function draw() {
    if (!img) return;
    var scale = baseScale() * parseFloat(zoom.value || '1');
    var w = img.width * scale, h = img.height * scale;
    var maxX = Math.max(0, (w - SIZE) / 2), maxY = Math.max(0, (h - SIZE) / 2);
    offset.x = Math.max(-maxX, Math.min(maxX, offset.x));
    offset.y = Math.max(-maxY, Math.min(maxY, offset.y));
    ctx.clearRect(0, 0, SIZE, SIZE);
    ctx.save();
    ctx.beginPath();
    ctx.arc(SIZE / 2, SIZE / 2, SIZE / 2, 0, Math.PI * 2);
    ctx.clip();
    ctx.drawImage(img, (SIZE - w) / 2 + offset.x, (SIZE - h) / 2 + offset.y, w, h);
    ctx.restore();
  }

  input.addEventListener('change', function () {
    var file = input.files && input.files[0];
    if (!file) { cropBox.hidden = true; img = null; return; }
    if (file.size > 2 * 1024 * 1024) {
      if (window.Swal) Swal.fire({ icon: 'warning', title: 'Imagen muy pesada', text: 'La foto no puede superar los 2 MB.', confirmButtonColor: '#920000' });
      input.value = '';
      return;
    }
    var reader = new FileReader();
    reader.onload = function () {
      var image = new Image();
      image.onload = function () {
        img = image;
        offset = { x: 0, y: 0 };
        zoom.value = '1';
        cropBox.hidden = false;
        draw();
      };
      image.src = reader.result;
    };
    reader.readAsDataURL(file);
  });

  zoom.addEventListener('input', draw);
  canvas.addEventListener('pointerdown', function (e) {
    if (!img) return;
    drag = { x: e.clientX, y: e.clientY, ox: offset.x, oy: offset.y };
    canvas.setPointerCapture(e.pointerId);
  });
  canvas.addEventListener('pointermove', function (e) {
    if (!drag) return;
    offset.x = drag.ox + (e.clientX - drag.x);
    offset.y = drag.oy + (e.clientY - drag.y);
    draw();
  });
  ['pointerup', 'pointercancel'].forEach(function (ev) {
    canvas.addEventListener(ev, function () { drag = null; });
  });

  form.addEventListener('submit', function (e) {
    var submitter = e.submitter;
    if (submitter && submitter.value === 'remove_photo') return;
    if (!img || !canvas.toBlob || !window.DataTransfer) return;  // envía la imagen original
    e.preventDefault();
    var out = document.createElement('canvas');
    out.width = OUT; out.height = OUT;
    var factor = OUT / SIZE;
    var scale = baseScale() * parseFloat(zoom.value || '1') * factor;
    var w = img.width * scale, h = img.height * scale;
    out.getContext('2d').drawImage(img, (OUT - w) / 2 + offset.x * factor, (OUT - h) / 2 + offset.y * factor, w, h);
    out.toBlob(function (blob) {
      if (!blob) { form.submit(); return; }
      var dt = new DataTransfer();
      dt.items.add(new File([blob], 'perfil.jpg', { type: 'image/jpeg' }));
      input.files = dt.files;
      img = null;  // evita recortar dos veces
      form.submit();
    }, 'image/jpeg', 0.9);
  });
})();
