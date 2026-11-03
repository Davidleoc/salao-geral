// Formulário de contratação — máscaras, validação e resumo do plano
// Usado em: app/templates/contratacao/form.html
// (extraído do template para facilitar a manutenção)

const precoMensal = parseFloat(document.getElementById('formContratacao').dataset.precoMensal);
const precoAnual = parseFloat(document.getElementById('formContratacao').dataset.precoAnual);
const brl = v => 'R$ ' + v.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

function atualizarResumo() {
  const anual = document.querySelector('input[name="periodicidade"]:checked').value === 'ANUAL';
  document.getElementById('resumoCiclo').textContent = anual ? 'Cobrança anual (12 meses)' : 'Cobrança mensal';
  document.getElementById('resumoValor').textContent = brl(anual ? precoAnual : precoMensal);
}

const $ = id => document.getElementById(id);
const form = $('formContratacao');

// ---- Slug automático a partir do nome
function gerarSlug(txt) {
  return txt.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '')
    .replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 100);
}
$('nome_salao').addEventListener('input', () => {
  if (!$('slug').dataset.manual) { $('slug').value = gerarSlug($('nome_salao').value); atualizarSlug(); }
});
$('slug').addEventListener('input', () => {
  $('slug').dataset.manual = '1';
  $('slug').value = $('slug').value.toLowerCase().replace(/[^a-z0-9-]/g, '');
  atualizarSlug();
});
function atualizarSlug() { $('slugPreviewText').textContent = $('slug').value || 'seu-negocio'; }

// ---- Telefone: só números, com máscara (11) 98888-7777
function mascaraTelefone(v) {
  const d = v.replace(/\D/g, '').slice(0, 11);
  if (d.length <= 2) return d.length ? '(' + d : '';
  if (d.length <= 6) return `(${d.slice(0,2)}) ${d.slice(2)}`;
  if (d.length <= 10) return `(${d.slice(0,2)}) ${d.slice(2,6)}-${d.slice(6)}`;
  return `(${d.slice(0,2)}) ${d.slice(2,7)}-${d.slice(7)}`;
}
function telefoneValido(v) {
  const d = v.replace(/\D/g, '');
  if (d.length !== 10 && d.length !== 11) return false;
  if (d[0] === '0' || d[1] === '0') return false;
  if (d.length === 11 && d[2] !== '9') return false;
  return true;
}
$('telefone').addEventListener('input', e => { e.target.value = mascaraTelefone(e.target.value); });
$('telefone').addEventListener('keypress', e => { if (e.key.length === 1 && !/\d/.test(e.key)) e.preventDefault(); });

// ---- CPF / CNPJ: máscara automática pelo tamanho + dígitos verificadores
function mascaraDocumento(v) {
  const d = v.replace(/\D/g, '').slice(0, 14);
  if (d.length <= 11) {
    return d.replace(/^(\d{3})(\d)/, '$1.$2').replace(/^(\d{3})\.(\d{3})(\d)/, '$1.$2.$3')
            .replace(/\.(\d{3})(\d{1,2})$/, '.$1-$2');
  }
  return d.replace(/^(\d{2})(\d)/, '$1.$2').replace(/^(\d{2})\.(\d{3})(\d)/, '$1.$2.$3')
          .replace(/\.(\d{3})(\d)/, '.$1/$2').replace(/(\d{4})(\d{1,2})$/, '$1-$2');
}
function cpfValido(d) {
  if (d.length !== 11 || /^(\d)\1+$/.test(d)) return false;
  for (const i of [9, 10]) {
    let soma = 0;
    for (let j = 0; j < i; j++) soma += +d[j] * (i + 1 - j);
    if (+d[i] !== (soma * 10 % 11) % 10) return false;
  }
  return true;
}
function cnpjValido(d) {
  if (d.length !== 14 || /^(\d)\1+$/.test(d)) return false;
  const pesos = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2];
  for (const n of [12, 13]) {
    let soma = 0;
    for (let i = 0; i < n; i++) soma += +d[i] * pesos[i + 13 - n];
    const dv = soma % 11 < 2 ? 0 : 11 - soma % 11;
    if (+d[n] !== dv) return false;
  }
  return true;
}
const documentoValido = v => { const d = v.replace(/\D/g, ''); return cpfValido(d) || cnpjValido(d); };
$('documento').addEventListener('input', e => { e.target.value = mascaraDocumento(e.target.value); });
$('documento').addEventListener('keypress', e => { if (e.key.length === 1 && !/\d/.test(e.key)) e.preventDefault(); });

// ---- E-mail: formato + sugestão para erros comuns de digitação
const reEmail = /^[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*\.[a-z]{2,}$/;
const dominiosErrados = {
  'gmial.com': 'gmail.com', 'gmai.com': 'gmail.com', 'gamil.com': 'gmail.com', 'gmail.con': 'gmail.com', 'gmail.com.br': 'gmail.com', 'gmail.co': 'gmail.com', 'gnail.com': 'gmail.com',
  'hotmal.com': 'hotmail.com', 'hotmial.com': 'hotmail.com', 'hotmail.con': 'hotmail.com', 'hotmai.com': 'hotmail.com',
  'outlok.com': 'outlook.com', 'outloo.com': 'outlook.com', 'outlook.con': 'outlook.com',
  'yahoo.com.b': 'yahoo.com.br', 'yaho.com.br': 'yahoo.com.br', 'icloud.con': 'icloud.com'
};
function verificarEmail() {
  const v = $('email').value.trim().toLowerCase();
  const sug = $('emailSugestao');
  sug.style.display = 'none';
  const dom = v.split('@')[1];
  if (dom && dominiosErrados[dom]) {
    const certo = v.split('@')[0] + '@' + dominiosErrados[dom];
    sug.innerHTML = 'Você quis dizer <a href="#" id="usarSug" style="color:var(--brand);font-weight:600;"></a>?';
    sug.querySelector('#usarSug').textContent = certo;
    sug.querySelector('#usarSug').onclick = ev => { ev.preventDefault(); $('email').value = certo; sug.style.display = 'none'; validar($('email')); };
    sug.style.display = 'block';
  }
}
$('email').addEventListener('blur', verificarEmail);

// ---- Regras de cada campo
const regras = {
  nome_salao: v => v.trim().length >= 2,
  slug: v => /^[a-z0-9]+(-[a-z0-9]+)*$/.test(v) && v.length >= 3,
  telefone: telefoneValido,
  documento: documentoValido,
  nome_responsavel: v => /^[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ'’.\- ]*$/.test(v.trim()) && v.trim().split(/\s+/).length >= 2,
  email: v => reEmail.test(v.trim().toLowerCase()),
  confirmar_email: v => v.trim().toLowerCase() === $('email').value.trim().toLowerCase() && v.trim() !== '',
  senha: v => v.length >= 8 && /[A-Za-z]/.test(v) && /\d/.test(v),
  confirmar_senha: v => v === $('senha').value && v !== '',
};
function validar(el) {
  const ok = regras[el.name](el.value);
  el.classList.toggle('is-invalid', !ok);
  el.classList.toggle('is-valid', ok);
  return ok;
}
Object.keys(regras).forEach(nome => {
  const el = form.elements[nome];
  el.addEventListener('blur', () => { if (el.value) validar(el); });
  el.addEventListener('input', () => { if (el.classList.contains('is-invalid')) validar(el); });
});

form.addEventListener('submit', e => {
  let primeiroErro = null;
  Object.keys(regras).forEach(nome => {
    const el = form.elements[nome];
    if (!validar(el) && !primeiroErro) primeiroErro = el;
  });
  const termos = $('aceite_termos');
  $('termosErro').style.display = termos.checked ? 'none' : 'block';
  if (!termos.checked && !primeiroErro) primeiroErro = termos;
  if (primeiroErro) {
    e.preventDefault();
    primeiroErro.focus();
    primeiroErro.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
});

if ($('telefone').value) $('telefone').value = mascaraTelefone($('telefone').value);
if ($('documento').value) $('documento').value = mascaraDocumento($('documento').value);
if ($('slug').value) $('slug').dataset.manual = '1';
atualizarResumo();
