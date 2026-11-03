// Página pública do salão — abas Serviços/Sobre e galeria
// Usado em: app/templates/public/salao.html
// (extraído do template para facilitar a manutenção)

(function () {
  const tabs = { servicos: document.getElementById('tab-servicos'), sobre: document.getElementById('tab-sobre') };
  function abrir(nome, atualizarHash) {
    Object.entries(tabs).forEach(([k, btn]) => {
      const ativo = k === nome;
      btn.setAttribute('aria-selected', ativo);
      document.getElementById('painel-' + k).hidden = !ativo;
    });
    if (atualizarHash) history.replaceState(null, '', nome === 'sobre' ? '#sobre' : location.pathname);
  }
  tabs.servicos.addEventListener('click', () => abrir('servicos', true));
  tabs.sobre.addEventListener('click', () => abrir('sobre', true));
  if (location.hash === '#sobre') abrir('sobre', false);

  const lb = document.getElementById('lightbox'), img = document.getElementById('lightboxImg');
  document.querySelectorAll('.gallery button').forEach(b => b.addEventListener('click', () => {
    img.src = b.dataset.src; lb.showModal();
  }));
  lb.addEventListener('click', e => { if (e.target === lb) lb.close(); });
})();
