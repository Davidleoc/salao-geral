// Animações de entrada compartilhadas por todas as telas
// Usado em: app/templates/base.html
// (extraído do template para facilitar a manutenção)

(function () {
  var reduz = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  // Elementos que ganham entrada suave, sem precisar editar cada tela
  var alvos = document.querySelectorAll('.kpi-card, .main-content .card, .admin-main-content .card, [data-rv]');
  if (!alvos.length) return;
  alvos.forEach(function (el, i) {
    el.classList.add('rv');
    el.style.transitionDelay = ((i % 6) * 60) + 'ms'; // leve escalonamento em grupos
  });

  function mostrar(el) { el.classList.add('in'); }
  function naTela(el) {
    var r = el.getBoundingClientRect();
    var h = window.innerHeight || document.documentElement.clientHeight;
    return r.top < h * 0.95 && r.bottom > 0;
  }

  if (reduz || !('IntersectionObserver' in window)) {
    alvos.forEach(mostrar);
    return;
  }

  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (e) {
      if (e.isIntersecting) { mostrar(e.target); io.unobserve(e.target); }
    });
  }, { threshold: 0.08 });

  alvos.forEach(function (el) {
    if (naTela(el)) mostrar(el);   // o que já está visível aparece na hora
    else io.observe(el);           // o resto anima ao rolar
  });

  // Rede de segurança: nada fica invisível (aba em segundo plano, observer que não dispara…)
  setTimeout(function () { alvos.forEach(mostrar); }, 1600);
})();
