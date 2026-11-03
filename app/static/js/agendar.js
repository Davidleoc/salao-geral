// Agendamento pelo cliente — profissional, horários livres, máscara, validação e lista de espera
// Usado em: app/templates/public/agendar.html (rota: routes/public.py)

const form = document.getElementById('formAgendamento');
const campoData = document.getElementById('data_agendamento');

function profissionalEscolhido() {
  const marcado = form.querySelector('input[name="profissional_id"]:checked');
  if (marcado) return marcado.value;
  const fixo = form.querySelector('input[name="profissional_id"]');
  return fixo ? fixo.value : '';
}

async function buscarHorarios() {
  const data = campoData.value;
  const grid = document.getElementById('grid_horarios');
  const semHorario = document.getElementById('msg_sem_horario');
  const carregando = document.getElementById('loading_horarios');

  grid.innerHTML = '';
  document.getElementById('hora_selecionada').value = '';
  const dados = document.getElementById('secao_dados');
  dados.style.display = 'none'; dados.style.opacity = '0';
  semHorario.style.display = 'none';
  document.getElementById('formEspera').hidden = true;
  if (!data) return;

  carregando.style.display = 'block';
  try {
    const prof = encodeURIComponent(profissionalEscolhido());
    const res = await fetch(`/api/public/${form.dataset.slug}/disponibilidade?servico_id=${form.dataset.servico}&data=${data}&profissional_id=${prof}`);
    const json = await res.json();
    carregando.style.display = 'none';
    if (json.horarios && json.horarios.length) {
      json.horarios.forEach(hora => {
        const b = document.createElement('button');
        b.type = 'button'; b.className = 'time-slot'; b.textContent = hora;
        b.onclick = () => selecionarHora(b, hora);
        grid.appendChild(b);
      });
    } else {
      semHorario.style.display = 'block';
    }
  } catch (e) {
    carregando.style.display = 'none';
    alert('Erro ao buscar horários. Tente novamente.');
  }
}

function selecionarHora(elemento, hora) {
  document.querySelectorAll('.time-slot').forEach(el => el.classList.remove('selected'));
  elemento.classList.add('selected');
  document.getElementById('hora_selecionada').value = hora;
  const dados = document.getElementById('secao_dados');
  dados.style.display = 'block';
  setTimeout(() => { dados.style.opacity = '1'; }, 50);
  dados.scrollIntoView({ behavior: 'smooth', block: 'end' });
}

// Máscara de WhatsApp: só números, (11) 90000-0000
function mascararTelefone(campo) {
  campo.addEventListener('input', () => {
    const d = campo.value.replace(/\D/g, '').slice(0, 11);
    if (d.length <= 2) campo.value = d.length ? '(' + d : '';
    else if (d.length <= 6) campo.value = `(${d.slice(0, 2)}) ${d.slice(2)}`;
    else if (d.length <= 10) campo.value = `(${d.slice(0, 2)}) ${d.slice(2, 6)}-${d.slice(6)}`;
    else campo.value = `(${d.slice(0, 2)}) ${d.slice(2, 7)}-${d.slice(7)}`;
  });
  campo.addEventListener('keypress', e => { if (e.key.length === 1 && !/\d/.test(e.key)) e.preventDefault(); });
}
document.querySelectorAll('.campo-tel').forEach(mascararTelefone);

function telefoneValido(valor) {
  const t = valor.replace(/\D/g, '');
  return (t.length === 10 || t.length === 11) && t[0] !== '0' && !(t.length === 11 && t[2] !== '9');
}

form.addEventListener('submit', e => {
  const nome = document.getElementById('ag_nome').value.trim();
  const email = document.getElementById('ag_email').value.trim();
  let msg = '';
  if (!document.getElementById('hora_selecionada').value) msg = 'Selecione um horário.';
  else if (!/^[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ'’.\- ]+$/.test(nome)) msg = 'Informe seu nome usando apenas letras.';
  else if (!telefoneValido(document.getElementById('ag_tel').value)) msg = 'WhatsApp inválido. Digite o DDD e o número.';
  else if (email && !/^[^\s@]+@[^\s@]+\.[a-z]{2,}$/i.test(email)) msg = 'E-mail inválido. Confira o endereço ou deixe em branco.';
  const box = document.getElementById('ag_erro');
  if (msg) { e.preventDefault(); box.textContent = '⚠ ' + msg; box.style.display = 'flex'; }
  else box.style.display = 'none';
});

// Lista de espera
document.getElementById('abrirEspera').addEventListener('click', () => {
  const espera = document.getElementById('formEspera');
  document.getElementById('espera_data').value = campoData.value;
  const prof = profissionalEscolhido();
  document.getElementById('espera_prof').value = prof === 'qualquer' ? '' : prof;
  const [a, m, d] = campoData.value.split('-');
  document.getElementById('espera_data_txt').textContent = `${d}/${m}/${a}`;
  espera.hidden = false;
  espera.scrollIntoView({ behavior: 'smooth', block: 'start' });
});

campoData.addEventListener('change', buscarHorarios);
form.querySelectorAll('input[name="profissional_id"]').forEach(r => r.addEventListener('change', buscarHorarios));
buscarHorarios();
