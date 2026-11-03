// Página de vendas /contratar — planos, cores, segmentos, avaliações e animações
// Usado em: app/templates/contratacao/planos.html
// (extraído do template para facilitar a manutenção)

// Alternância mensal / anual
function setBilling(mode) {
  const anual = mode === 'anual';
  document.getElementById('btnMensal').classList.toggle('active', !anual);
  document.getElementById('btnAnual').classList.toggle('active', anual);
  document.querySelectorAll('.price-mensal').forEach(el => el.style.display = anual ? 'none' : 'block');
  document.querySelectorAll('.price-anual').forEach(el => el.style.display = anual ? 'block' : 'none');
  document.querySelectorAll('[data-plano-id]').forEach(btn => {
    btn.href = '/contratar/' + btn.dataset.planoId + '?periodicidade=' + (anual ? 'ANUAL' : 'MENSAL');
  });
}

// Prévia de cores
const preview = document.getElementById('previewCores');
document.querySelectorAll('.swatch').forEach(sw => {
  sw.addEventListener('click', () => {
    document.querySelectorAll('.swatch').forEach(s => s.classList.remove('on'));
    sw.classList.add('on');
    preview.style.setProperty('--pv-brand', sw.dataset.a);
    preview.style.setProperty('--pv-accent', sw.dataset.b);
  });
});

// Avaliação: estrelas de 0,5 em 0,5 (só quando o formulário está presente — contratante logado)
const formAval = document.getElementById('formAvaliacao');
if (formAval) {
  const range = document.getElementById('aval_nota');
  const fill = document.getElementById('rateFill');
  const label = document.getElementById('rateLabel');
  const notaHidden = document.getElementById('notaHidden');
  const rateBox = document.getElementById('rateBox');
  const pintar = v => { fill.style.width = (v / 5 * 100) + '%'; };
  function escolher(v) {
    notaHidden.value = v;
    label.textContent = String(v).replace('.', ',');
    label.style.color = '#111827';
    pintar(v);
  }
  function valorPeloMouse(e) {
    const r = rateBox.getBoundingClientRect();
    const x = Math.min(Math.max(e.clientX - r.left, 0), r.width);
    return Math.max(0.5, Math.ceil((x / r.width) * 10) / 2);
  }
  rateBox.addEventListener('mousemove', e => pintar(valorPeloMouse(e)));
  rateBox.addEventListener('mouseleave', () => pintar(notaHidden.value || 0));
  rateBox.addEventListener('click', e => { const v = valorPeloMouse(e); range.value = v; escolher(v); });
  range.addEventListener('input', () => escolher(parseFloat(range.value)));

  const coment = document.getElementById('aval_coment');
  const count = document.getElementById('comentCount');
  coment.addEventListener('input', () => count.textContent = coment.value.length);

  formAval.addEventListener('submit', e => {
    const erroBox = document.getElementById('avalErroJs');
    let msg = '';
    if (!notaHidden.value) msg = 'Selecione uma nota clicando nas estrelas.';
    else if (coment.value.trim().length < 10) msg = 'Escreva um comentário com pelo menos 10 caracteres.';
    if (msg) { e.preventDefault(); erroBox.textContent = '⚠ ' + msg; erroBox.style.display = 'flex'; }
  });
}

// Seletor de segmentos — mostra uma mensagem feita para cada nicho
(function () {
  const chips = document.querySelectorAll('#segChips .lp-seg');
  const panel = document.getElementById('segPanel');
  const pIcon = document.getElementById('segPanelIcon');
  const pHead = document.getElementById('segPanelHead');
  const pMsg = document.getElementById('segPanelMsg');
  const pTags = document.getElementById('segPanelTags');
  if (!chips.length || !panel) return;

  function aplicar(chip) {
    chips.forEach(c => c.classList.remove('active'));
    chip.classList.add('active');
    pHead.textContent = chip.dataset.head;
    pMsg.textContent = chip.dataset.msg;
    const svg = chip.querySelector('svg');
    if (svg) pIcon.innerHTML = svg.outerHTML.replace('width="18"', 'width="26"').replace('height="18"', 'height="26"');
    pTags.innerHTML = '';
    (chip.dataset.tags || '').split('|').forEach(t => {
      if (!t) return;
      const s = document.createElement('span'); s.textContent = t; pTags.appendChild(s);
    });
    [pHead, pMsg, pTags, pIcon].forEach(el => {
      el.classList.remove('seg-anim'); void el.offsetWidth; el.classList.add('seg-anim');
    });
  }

  chips.forEach(chip => chip.addEventListener('click', () => aplicar(chip)));
})();

// Animação de entrada das seções ao rolar
(function () {
  const alvos = document.querySelectorAll('[data-reveal]');
  if (!('IntersectionObserver' in window) || !alvos.length) {
    alvos.forEach(el => el.classList.add('in')); return;
  }
  const io = new IntersectionObserver((entries) => {
    entries.forEach(e => { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); } });
  }, { threshold: 0.12 });
  alvos.forEach(el => io.observe(el));
})();

// Calculadora de faltas — conta simples e transparente (premissa explicada na tela)
(function () {
  const calc = document.querySelector('.calc');
  if (!calc) return;
  const $ = id => document.getElementById(id);
  const reducao = parseFloat(calc.dataset.reducao || '30') / 100;
  const preco = parseFloat(calc.dataset.preco || '0');
  const brl = v => 'R$ ' + Math.round(v).toLocaleString('pt-BR');
  const SEMANAS_NO_MES = 4.33;

  function contar() {
    const atend = +$('calcAtend').value, ticket = +$('calcTicket').value, faltas = +$('calcFaltas').value / 100;
    $('calcAtendOut').textContent = atend;
    $('calcTicketOut').textContent = brl(ticket);
    $('calcFaltasOut').textContent = Math.round(faltas * 100) + '%';
    const vazios = atend * SEMANAS_NO_MES * faltas;
    const perde = vazios * ticket;
    const recupera = perde * reducao;
    $('calcPerde').textContent = brl(perde);
    $('calcPerdeQtd').textContent = Math.round(vazios) + ' horário' + (Math.round(vazios) === 1 ? '' : 's') + ' vazio' + (Math.round(vazios) === 1 ? '' : 's') + ' por mês';
    $('calcRecupera').textContent = brl(recupera);
    const compara = $('calcCompara');
    if (compara && preco) {
      const vezes = recupera / preco;
      compara.textContent = vezes >= 1.1
        ? `É ${vezes.toLocaleString('pt-BR', { maximumFractionDigits: 1 })}× o valor do plano Pro (R$ ${preco.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}/mês).`
        : `O plano Pro custa R$ ${preco.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}/mês.`;
    }
    // Preenche a trilha do slider até o ponto escolhido
    calc.querySelectorAll('input[type=range]').forEach(r => {
      r.style.setProperty('--p', ((r.value - r.min) / (r.max - r.min) * 100) + '%');
    });
  }
  calc.querySelectorAll('input[type=range]').forEach(r => r.addEventListener('input', contar));
  contar();
})();
