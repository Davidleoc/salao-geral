# Guia do projeto — onde fica cada coisa

Sistema de agendamento e gestão para negócios com hora marcada (salões, barbearias, estúdios…).
Feito com **FastAPI** (Python) + **Jinja2** (HTML) + **SQLAlchemy** (banco) + **Alembic** (migrações).

---

## "Quero mudar…" → abra este arquivo

| Quero mudar… | Arquivo |
|---|---|
| Textos da página de vendas (`/contratar`) | `app/textos/landing.py` |
| Textos da tela de login | `app/textos/login.py` |
| Textos fixos da página pública do salão (`/{slug}`) | `app/textos/salao_publico.py` |
| Termos de Uso / LGPD | `app/templates/contratacao/termos.html` |
| Paletas de cores prontas | `app/paletas.py` |
| Ícones (desenho SVG) | `app/icons.py` |
| Preços, limites e recursos de cada plano | Tela `/admin/planos` (fica no banco, não no código) |
| Cores, fontes e componentes gerais (botões, cards, tabelas) | `app/static/css/style.css` |
| Visual de uma tela específica | `app/static/css/<tela>.css` (tabela abaixo) |
| Comportamento (JavaScript) de uma tela | `app/static/js/<tela>.js` (tabela abaixo) |
| Telas ilustrativas da página de vendas | `app/templates/contratacao/mockups/` |
| Regras de validação (telefone, e-mail, senha, valores) | `app/validacao.py` |
| E-mails enviados (conteúdo) | `app/templates/emails/` · envio em `app/services/email_service.py` |
| Cálculo de horários livres | `app/services/disponibilidade_service.py` |
| Configurações (chave secreta, banco, MFA, SMTP, dias de teste, cobrança, LGPD) | `.env` (modelo em `.env.example`) · leitura em `app/config.py` |
| O que cada função (dono, gerente, funcionário) pode fazer | `app/permissoes.py` |
| Régua de cobrança (teste grátis, vencimento, atraso, suspensão) | `app/services/cobranca.py` |
| Tarefas automáticas (lembretes, cobrança, lista de espera, LGPD) | `app/services/tarefas.py` |
| Limites de tentativas por IP | `app/services/limite_taxa.py` → `LIMITES` |
| Retenção, exportação e anonimização (LGPD) | `app/services/lgpd.py` |
| Notificações rápidas na tela (sininho) | `app/services/notificacoes.py` · `static/js/notificacoes.js` |

> **Textos:** abra o arquivo em `app/textos/`, altere só o que está **entre aspas**, salve e recarregue a página.
> Com o servidor rodando com `--reload`, ele reinicia sozinho.

---

## Cada tela e seus arquivos

| Tela | URL | Rota (Python) | HTML | CSS | JS |
|---|---|---|---|---|---|
| Página de vendas | `/contratar` | `routes/contratacao.py` | `contratacao/planos.html` | `landing.css` | `landing.js` |
| Formulário de contratação | `/contratar/{plano}` | `routes/contratacao.py` | `contratacao/form.html` | `contratar-form.css` | `contratar-form.js` |
| Sucesso da contratação | `/contratar/sucesso` | `routes/contratacao.py` | `contratacao/sucesso.html` | `contratar-sucesso.css` | — |
| Termos / LGPD | `/termos` | `routes/contratacao.py` | `contratacao/termos.html` | `termos.css` | — |
| Página pública do salão | `/{slug}` | `routes/public.py` | `public/salao.html` | `salao-publico.css` | `salao-publico.js` |
| Agendamento pelo cliente | `/{slug}/agendar/{id}` | `routes/public.py` | `public/agendar.html` | `agendar.css` | `agendar.js` |
| Login, recuperar senha, MFA | `/minhaagenda/login` … | `routes/auth.py` | `auth/*.html` | `style.css` | (inline, pequeno) |
| Painel: dashboard | `/minhaagenda/dashboard` | `routes/dashboard.py` | `painel/dashboard.html` | `style.css` | — |
| Painel: agenda | `/minhaagenda/agenda` | `routes/agenda.py` | `painel/agenda*.html` | `style.css` | — |
| Painel: clientes | `/minhaagenda/clientes` | `routes/clientes.py` | `painel/cliente*.html` | `style.css` | — |
| Painel: serviços | `/minhaagenda/servicos` | `routes/servicos.py` | `painel/servico*.html` | `style.css` | (inline) |
| Painel: relatórios / CSV | `/minhaagenda/relatorios` | `routes/relatorios.py` | `painel/relatorios.html` | `style.css` | — |
| Painel: configurações, horários, fotos | `/minhaagenda/configuracoes` | `routes/configuracoes.py` | `painel/configuracoes.html`, `horarios.html` | `style.css` | (inline) |
| Painel: equipe, convites, comissões, meus ganhos, perfil | `/minhaagenda/equipe` … | `routes/equipe.py` | `painel/equipe.html`, `comissoes.html`, `meus_ganhos.html`, `perfil.html` | `style.css` | — |
| Aceitar convite da equipe | `/convite/{token}` | `routes/equipe.py` | `auth/convite.html` | `style.css` | — |
| Painel: pacotes, lista de espera, avaliações | `/minhaagenda/pacotes` … | `routes/extras.py` | `painel/pacotes.html`, `lista_espera.html`, `avaliacoes.html` | `style.css` | — |
| Cliente avalia o atendimento | `/avaliar/{token}` | `routes/extras.py` | `public/avaliar.html` | (inline) | — |
| Calendário (Google Agenda) | `/calendario/{token}.ics` | `routes/extras.py` | — | — | — |
| Painel: assinatura, baixar dados, encerrar conta | `/minhaagenda/assinatura` | `routes/conta.py` | `painel/assinatura.html`, `conta_bloqueada.html` | `style.css` | — |
| Notificações (API do sininho) | `/api/notificacoes` | `routes/notificacoes.py` | — | — | `notificacoes.js` |
| Admin do SaaS | `/admin` | `routes/admin.py` | `admin/*.html` | `admin.css` | — |
| Admin: financeiro | `/admin/financeiro` | `routes/admin_financeiro.py` | `admin/financeiro.html` | `admin.css` | — |
| Admin: pedidos de senha, auditoria | `/admin/senhas`, `/admin/auditoria` | `routes/admin_seguranca.py` | `admin/senhas.html`, `auditoria.html` | `admin.css` | — |
| Painel de testes (só desenvolvimento) | `/dev` | `routes/dev.py` | `dev/*.html` | — | — |

Todas as telas herdam de `templates/base.html` (cabeçalho, favicon, animações em `static/js/animacoes.js`).
O painel do salão herda de `painel/painel_base.html` (menu lateral) e o admin de `admin/admin_base.html`.

---

## Estrutura de pastas

```
app/
├── main.py              Liga tudo: registra as rotas e os arquivos estáticos
├── config.py            Lê o .env (chave secreta, banco, MFA_ENABLED…)
├── database.py          Conexão com o banco
├── deps.py              "Quem está logado?" — usado pelas rotas (obter_usuario_atual, exigir_admin…)
├── permissoes.py        O que dono, gerente e funcionário podem fazer
├── csrf.py              Proteção CSRF: todo <form method="post"> precisa de {{ csrf_input() }}
├── tenant.py            Isolamento entre salões: toda consulta do painel passa por aqui
├── security.py          Senhas (Argon2), tokens de sessão (JWT), MFA, recuperação de senha
├── validacao.py         Validação de telefone, e-mail, nome, senha e valores em R$
├── templates_compat.py  Configuração do Jinja: filtros (brl, com_numero, link_whatsapp, status_label)
│                        e funções globais dos templates (icon, textos, asset)
├── icons.py             Desenhos dos ícones SVG
├── paletas.py           Paletas de cores prontas
├── textos/              TEXTOS DAS TELAS (edite aqui)
├── models/              Tabelas do banco (uma por arquivo)
├── routes/              Rotas/telas, uma área por arquivo (ver tabela acima)
├── services/            Regras reutilizáveis
│   ├── auditoria.py         registrar_evento(): log de segurança padronizado
│   ├── disponibilidade_service.py  horários livres (por profissional)
│   ├── email_service.py     e-mails (SMTP se configurado; senão ficam em /dev/emails)
│   ├── cobranca.py          teste grátis, Pix, vencimento, atraso, suspensão
│   ├── tarefas.py           tarefas automáticas (roda dentro do servidor a cada 10 min)
│   ├── equipe.py · comissoes.py · contas.py   convites, comissões, e-mail/senha
│   ├── pacotes.py · lista_espera.py · avaliacoes.py
│   ├── financeiro.py        MRR e números do admin
│   ├── lgpd.py              baixar dados, encerrar conta, retenção automática
│   ├── limite_taxa.py       limite de tentativas por IP
│   └── notificacoes.py      avisos na tela (sininho)
├── static/
│   ├── css/  style.css (global) + um arquivo por tela
│   ├── js/   um arquivo por tela + animacoes.js (todas as telas)
│   ├── img/  favicons
│   └── uploads/  fotos enviadas pelos salões (fora do git)
└── templates/           HTML (Jinja2), uma pasta por área
migrations/              Alterações do banco (Alembic)
tests/                   Testes automáticos
```

---

## Regras do projeto (para manter organizado)

1. **Texto que aparece na tela** → em `app/textos/` quando a tela já tem arquivo de textos. Para uma tela nova, crie `app/textos/<tela>.py` e registre em `app/textos/__init__.py`.
2. **CSS/JS de mais de ~20 linhas** → arquivo em `static/css` ou `static/js`, com o mesmo nome da tela, incluído com `{{ asset('css/x.css') }}`. O `asset()` acrescenta a versão do arquivo ao link, então o navegador sempre pega a versão nova.
3. **Valores do banco dentro de JS** → passe por atributo `data-` no HTML (ex: `data-slug="{{ salao.slug }}"`) e leia no JS com `elemento.dataset.slug`. Não escreva `{{ }}` dentro de arquivos `.js`.
4. **Consultas do painel do salão** → sempre via `tenant.query(...)` / `tenant.get_or_404(...)`. Nunca use o `salao_id` vindo da URL ou do formulário.
5. **Eventos de segurança** (login, alterações, cancelamentos) → `registrar_evento(...)` de `services/auditoria.py`.
6. **Dados digitados** (telefone, e-mail, valores) → valide no servidor com `validacao.py`. O JS das telas serve só para conforto.
7. **Mudou uma tabela do banco** → crie uma migração em `migrations/versions/` e rode `alembic upgrade head`.
8. **Formulário POST** → coloque `{{ csrf_input() }}` logo depois da tag `<form>`. Sem isso o envio é recusado (403).
9. **Tela do painel** → depois de `obter_tenant(...)`, chame `tenant.exigir("permissao")` (lista em `permissoes.py`). No HTML, use `{% if pode('permissao') %}`.
10. **Avisar alguém na tela** → `notificar_salao(...)` ou `notificar_admin(...)` de `services/notificacoes.py`.

---

## Como rodar

```bash
venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 9080 --reload
```

- Site: http://localhost:9080/contratar
- Painel de testes (entrar como qualquer usuário, simular pagamento, gerar dados, rodar as tarefas automáticas, ver os e-mails): http://localhost:9080/dev
- Documentação automática das rotas: http://localhost:9080/docs

Atualizar o banco depois de puxar mudanças:

```bash
venv\Scripts\alembic.exe upgrade head
```

## Como testar

```bash
venv\Scripts\python.exe -m pytest -q
```

Os testes rodam num banco temporário (não mexem no `sql_app.db`). Cobrem: páginas públicas e arquivos
estáticos, textos, contratação (validações), avaliações, isolamento entre salões, permissões de admin,
tokens forjados, MFA pendente, custos/lucro e agendamento pelo cliente — e, em `tests/test_recursos.py`:
CSRF, limite por IP, convite de uso único, permissões do funcionário, gerente fora do Básico, pedido de senha
pelo admin, régua de cobrança, conta bloqueada, lista de espera, pacotes, avaliação + Google, calendário,
baixar dados/encerrar conta/anonimização e as telas do admin.
Rode antes de publicar qualquer mudança.

## Antes de colocar em produção

- `APP_ENV=production` no `.env` (desliga `/dev` e `/docs`, liga cookies `secure`).
- `SECRET_KEY` forte e única (o sistema se recusa a iniciar com uma chave fraca em produção).
- Banco PostgreSQL em vez de SQLite.
- Ligar o envio real de e-mails: `SMTP_HOST`, `SMTP_USUARIO`, `SMTP_SENHA`, `EMAIL_FROM` e `URL_BASE` (endereço público) no `.env`.
- `PIX_CHAVE` para os e-mails de cobrança saírem com o Pix copia e cola.
- `CHAVE_CRIPTOGRAFIA` própria (protege o segredo do MFA no banco).
- Atrás de nginx/Cloudflare: `CONFIAR_PROXY=true` (para o limite por IP ver o IP real).
- Com mais de um servidor: trocar o limite por IP em memória (`limite_taxa.py`) por Redis.
- HTTPS no servidor.
