// Notificações na tela: sininho com contador + balões no canto (painel do salão e /admin)
// Precisa de: <div id="notif" data-ultimo-id="..."> no topo da página (painel_base.html / admin_base.html)
// Consulta /api/notificacoes a cada 20s, só enquanto a aba está visível (economiza servidor e bateria).

(function () {
  const raiz = document.getElementById('notif');
  if (!raiz) return;

  const botao = raiz.querySelector('.notif-botao');
  const contador = raiz.querySelector('.notif-contador');
  const painel = raiz.querySelector('.notif-painel');
  const listaEl = raiz.querySelector('.notif-lista');
  const toasts = document.getElementById('toasts');
  let ultimoId = parseInt(raiz.dataset.ultimoId || '0', 10);
  let timer = null;

  const csrf = () => (document.cookie.match(/(?:^|; )csrf_token=([^;]+)/) || [])[1] || '';

  function escapar(t) {
    const d = document.createElement('div'); d.textContent = t || ''; return d.innerHTML;
  }

  function atualizarContador(n) {
    contador.textContent = n > 9 ? '9+' : String(n);
    contador.hidden = n === 0;
    botao.setAttribute('aria-label', n ? `${n} notificações não lidas` : 'Notificações');
  }

  function desenharLista(itens) {
    if (!itens.length) { listaEl.innerHTML = '<div class="notif-vazio">Nenhuma notificação ainda.</div>'; return; }
    listaEl.innerHTML = itens.map(n => `
      <a class="notif-item${n.lida ? '' : ' nova'}" href="${n.link ? escapar(n.link) : '#'}">
        <span class="notif-ponto"></span>
        <span><b>${escapar(n.titulo)}</b><small>${escapar(n.mensagem)}</small><em>${escapar(n.quando)}</em></span>
      </a>`).join('');
  }

  function mostrarToast(n) {
    if (!toasts) return;
    const el = document.createElement(n.link ? 'a' : 'div');
    el.className = 'toast';
    if (n.link) el.href = n.link;
    el.innerHTML = `<b>${escapar(n.titulo)}</b><span>${escapar(n.mensagem)}</span>`;
    toasts.appendChild(el);
    requestAnimationFrame(() => el.classList.add('mostrar'));
    setTimeout(() => { el.classList.remove('mostrar'); setTimeout(() => el.remove(), 400); }, 6000);
  }

  async function consultar() {
    try {
      const r = await fetch(`/api/notificacoes?desde=${ultimoId}`, { headers: { 'Accept': 'application/json' } });
      if (!r.ok) return;
      const d = await r.json();
      d.novas.forEach(mostrarToast);
      if (d.ultimo_id > ultimoId) ultimoId = d.ultimo_id;
      atualizarContador(d.nao_lidas);
      desenharLista(d.lista);
    } catch (e) { /* sem conexão: tenta de novo no próximo ciclo */ }
  }

  function iniciar() { if (!timer) timer = setInterval(consultar, 20000); }
  function parar() { clearInterval(timer); timer = null; }

  botao.addEventListener('click', async (e) => {
    e.stopPropagation();
    const abrir = painel.hidden;
    painel.hidden = !abrir;
    if (abrir && contador.textContent !== '0' && !contador.hidden) {
      await fetch('/api/notificacoes/lidas', { method: 'POST', headers: { 'X-CSRF-Token': csrf() } });
      atualizarContador(0);
    }
  });
  document.addEventListener('click', (e) => { if (!raiz.contains(e.target)) painel.hidden = true; });

  document.addEventListener('visibilitychange', () => {
    if (document.hidden) parar(); else { consultar(); iniciar(); }
  });

  // Mensagem de sucesso da própria ação (?mensagem=...) também vira balão
  const msg = document.querySelector('[data-toast-mensagem]');
  if (msg) mostrarToast({ titulo: '✓ ' + msg.dataset.toastMensagem, mensagem: '' });

  consultar();
  iniciar();
})();
