"""
TEXTOS DA PÁGINA DE VENDAS (/contratar)
Template: app/templates/contratacao/planos.html

Como editar:
  - Altere só o que está entre aspas. Mantenha as vírgulas e os colchetes.
  - Para incluir um item numa lista, copie um item existente (de { até },) e edite.
  - Ícones disponíveis: veja os nomes em app/icons.py (ex: 'calendar', 'scissors').
  - Depois de salvar, basta recarregar a página (o servidor reinicia sozinho).
"""

PAGINA = {
    "titulo": "MeuAgendamento — Agenda e gestão para salões, barbearias e estúdios",
    "descricao_seo": "Agenda online 24h, controle de clientes, custos e lucro por serviço. Para salões de beleza, barbearias, manicures, estética e outros negócios com hora marcada.",
}

MENU = {
    "recursos": "Recursos",
    "planos": "Planos",
    "avaliacoes": "Avaliações",
    "entrar": "Já sou cliente (Entrar)",
}

# ---------------------------------------------------------------- Topo (hero)
HERO = {
    "etiqueta": "Agenda + gestão do seu negócio",
    # O título é dividido em 3 partes: a do meio aparece em destaque (gradiente)
    "titulo_antes": "Sua agenda cheia e o",
    "titulo_destaque": "lucro de cada serviço",
    "titulo_depois": "na palma da mão",
    "texto": (
        "O MeuAgendamento é o sistema para quem trabalha com hora marcada: salões de beleza, "
        "barbearias, manicures, estética, sobrancelhas e cílios, massoterapia e muito mais. "
        "Seus clientes agendam sozinhos, 24 horas por dia, e você acompanha agenda, clientes, "
        "custos e lucro em um só lugar."
    ),
    "botao_principal": "Testar 12 dias grátis",
    "botao_secundario": "Conhecer os recursos",
    "garantias": ["12 dias grátis, sem cartão", "Sem fidelidade", "Funciona no celular"],
    # Cartões flutuantes sobre a tela ilustrativa
    "cartao_1_titulo": "Novo agendamento",
    "cartao_1_texto": "Juliana · hoje às 09:00",
    "cartao_2_titulo": "Lucro do mês +32%",
    "cartao_2_texto": "vs. mês anterior",
}

# ---------------------------------------------------------------- Segmentos
SEGMENTOS_CHAMADA = "Feito para o seu tipo de negócio"
SEGMENTOS_DICA = "— toque no seu"
SEGMENTOS_BOTAO = "Começar agora"

SEGMENTOS = [
    {
        "icone": "scissors",
        "nome": "Salões de beleza",
        "mensagem": "Cortes, coloração, escova e tratamentos com agenda cheia o dia todo. O cliente reserva online e recebe lembrete — você reduz faltas e encaixa melhor a equipe.",
        "tags": ["Corte", "Coloração", "Escova", "Hidratação"],
    },
    {
        "icone": "comb",
        "nome": "Barbearias",
        "mensagem": "Corte, barba e combos sem fila bagunçada. Seus clientes marcam pelo Instagram e você controla cada profissional em uma só tela.",
        "tags": ["Corte", "Barba", "Corte + Barba", "Pigmentação"],
    },
    {
        "icone": "hand",
        "nome": "Manicure e pedicure",
        "mensagem": "Mão, pé e alongamento com horários certinhos e duração real de cada serviço — nada de encaixe que atrasa o dia inteiro.",
        "tags": ["Manicure", "Pedicure", "Alongamento", "Esmaltação em gel"],
    },
    {
        "icone": "sparkles",
        "nome": "Estética e skincare",
        "mensagem": "Limpeza de pele, peelings e protocolos com o histórico de cada cliente à mão, para acompanhar a evolução e fidelizar.",
        "tags": ["Limpeza de pele", "Peeling", "Microagulhamento", "Massagem facial"],
    },
    {
        "icone": "eye",
        "nome": "Sobrancelhas e cílios",
        "mensagem": "Design, henna e extensão com o retorno já sugerido na agenda. O cliente volta na hora certa da manutenção.",
        "tags": ["Design", "Henna", "Volume russo", "Lash lifting"],
    },
    {
        "icone": "heart",
        "nome": "Massoterapia",
        "mensagem": "Sessões com duração exata, intervalos de descanso bloqueados automaticamente e lembrete de retorno para manter a rotina do cliente.",
        "tags": ["Relaxante", "Drenagem", "Pedras quentes", "Quick massage"],
    },
    {
        "icone": "tattoo",
        "nome": "Estúdios de tatuagem",
        "mensagem": "Orçamento, sinal e sessões longas sem conflito de horário. Cada artista com a própria agenda e o próprio portfólio na página.",
        "tags": ["Orçamento", "Sessão", "Retoque", "Piercing"],
    },
    {
        "icone": "paw",
        "nome": "Pet shops e banho e tosa",
        "mensagem": "Banho, tosa e vacinas com agenda por profissional e aviso ao tutor. Menos telefone tocando, mais pets atendidos.",
        "tags": ["Banho", "Tosa", "Hidratação", "Vacina"],
    },
]

# ---------------------------------------------------------------- Recursos em destaque
RECURSOS = {
    "etiqueta": "Recursos",
    "titulo": "Tudo o que você precisa para organizar e fazer o negócio crescer",
    "texto": "Do primeiro agendamento ao relatório de lucro do mês, sem planilhas e sem caderno.",
}

# Cada destaque mostra um texto ao lado de uma tela ilustrativa.
# "mockup" = nome do arquivo em app/templates/contratacao/mockups/ (sem .html)
# Use {paletas} para inserir a quantidade de paletas de cores disponíveis.
DESTAQUES = [
    {
        "mockup": "agendamento",
        "etiqueta": "Agendamento online 24h",
        "titulo": "Seus clientes marcam sozinhos, a qualquer hora",
        "texto": "Você ganha um link próprio (ex: meuagendamento.com/seu-negocio) para divulgar no Instagram, no WhatsApp e no Google.",
        "itens": [
            "O cliente escolhe o serviço, o dia e só vê os horários realmente livres",
            "Sem agendamento duplicado: o sistema respeita duração do serviço, almoço, feriados e bloqueios",
            "Confirmação por e-mail para o cliente e aviso de novo agendamento para você",
        ],
    },
    {
        "mockup": "lista_agendamentos",
        "etiqueta": "Monitore seus agendamentos",
        "titulo": "Saiba exatamente quem vem, quando e o que já foi feito",
        "texto": "A agenda do dia e da semana em uma tela, com o status de cada atendimento.",
        "itens": [
            "Marque como confirmado, concluído, cancelado ou “não compareceu” em um clique",
            "Agende pelo painel quando o cliente ligar ou mandar mensagem",
            "Ficha completa do cliente, com histórico de visitas, gastos e observações (alergias, preferências)",
        ],
    },
    {
        "mockup": "lucro",
        "etiqueta": "Custos e lucro",
        "titulo": "Descubra quanto cada serviço realmente coloca no seu bolso",
        "texto": "Cadastre quanto custa prestar cada serviço (produtos, materiais, comissão) e o sistema calcula o lucro automaticamente.",
        "itens": [
            "Faturamento, custos e lucro do período em destaque",
            "Lucro por serviço e margem em %: veja quais serviços valem mais a pena",
            "Ticket médio, cancelamentos e clientes mais fiéis",
            "Exportação em CSV para o seu contador (plano Premium)",
        ],
    },
    {
        "mockup": "equipe",
        "etiqueta": "Equipe e comissões",
        "titulo": "Cada profissional com a sua agenda — e a comissão calculada sozinha",
        "texto": "Convide sua equipe por e-mail com um link único. Cada pessoa entra com a própria senha e vê só o que a função dela permite.",
        "itens": [
            "Dono, gerente e funcionário: o funcionário vê só a própria agenda e quanto ganhou, nunca o lucro do salão",
            "O cliente escolhe com quem quer ser atendido, com foto e especialidade (ex: cabeleireira, barbeiro)",
            "Relatório de comissões do mês por profissional, com o lucro real do salão já descontado",
            "Função de gerente e agenda no Google Agenda a partir do plano Pro",
        ],
    },
    {
        "mockup": "cores",
        "etiqueta": "Sua marca, suas cores",
        "titulo": "Personalize a tela do seu agendamento com as cores que preferir",
        "texto": "A página que seus clientes acessam fica com a cara do seu negócio: cores, logo, descrição e uma aba “Sobre” com fotos do espaço.",
        "itens": [
            "{paletas} paletas prontas ou qualquer combinação de cor principal e secundária, com prévia na hora",
            "Aba “Sobre” com texto de apresentação e galeria de fotos (até 5 fotos no Pro e 10 no Premium)",
            "Endereço, WhatsApp e Instagram sempre à vista do cliente",
        ],
        "chamada_cores": "Experimente, clique em uma cor:",
    },
]

# ---------------------------------------------------------------- Grade "E ainda tem muito mais"
MAIS_RECURSOS_TITULO = "E ainda tem muito mais"
MAIS_RECURSOS = [
    {"icone": "mail", "titulo": "Lembretes automáticos", "texto": "O cliente recebe um lembrete por e-mail um dia antes do horário — menos esquecimentos e menos faltas (Pro e Premium)."},
    {"icone": "clock", "titulo": "Lista de espera", "texto": "Dia lotado? O cliente entra na fila. Se alguém desmarcar, o primeiro é avisado na hora e o horário não fica vazio."},
    {"icone": "card", "titulo": "Pacotes e clube de assinatura", "texto": "Venda 4 escovas, 10 sessões ou um clube mensal. O sistema desconta cada sessão usada e avisa o vencimento."},
    {"icone": "star", "titulo": "Avaliação do atendimento", "texto": "Depois do serviço, o cliente dá uma nota. Quem gostou é convidado a avaliar você também no Google."},
    {"icone": "calendar", "titulo": "Google Agenda", "texto": "Cada profissional vê os próprios horários no Google Agenda e no celular, atualizados sozinhos (Pro e Premium)."},
    {"icone": "ban", "titulo": "Bloqueios e feriados", "texto": "Feche a agenda em feriados, folgas ou cursos, o dia inteiro ou só por algumas horas."},
    {"icone": "download", "titulo": "Seus dados são seus", "texto": "Baixe tudo em planilha a qualquer momento, em qualquer plano. CSV pronto para o contador no Premium."},
    {"icone": "shield-check", "titulo": "Segurança e LGPD", "texto": "Confirmação de e-mail, senhas criptografadas, proteção contra robôs e cada negócio com seus dados isolados."},
]

# ---------------------------------------------------------------- Calculadora de faltas (interativa)
# A conta é feita no navegador (static/js/landing.js). "reducao" é a estimativa usada e aparece explicada na tela.
CALCULADORA = {
    "etiqueta": "Faça a conta",
    "titulo": "Quanto as faltas custam para o seu negócio?",
    "texto": "Mexa nos números com a realidade do seu negócio.",
    "atendimentos": "Atendimentos por semana",
    "ticket": "Valor médio do atendimento",
    "faltas": "Clientes que faltam sem avisar",
    "perde_titulo": "Você perde por mês com faltas",
    "recupera_titulo": "Dá para recuperar por mês",
    "reducao": 30,
    "premissa": (
        "Estimativa, não promessa: consideramos que lembrete um dia antes e lista de espera evitem ou "
        "reponham cerca de {reducao}% das faltas. O resultado real depende dos seus clientes."
    ),
    "comparacao": "O plano Pro custa R$ {preco} por mês.",
    "botao": "Testar 12 dias grátis",
}

# ---------------------------------------------------------------- Planos
PLANOS = {
    "etiqueta": "Planos",
    "titulo": "Escolha o plano ideal para o seu negócio",
    "texto": "Comece com 12 dias grátis, sem cartão. Sem fidelidade e sem taxa de cancelamento.",
    "mensal": "Mensal",
    "anual": "Anual",
    "desconto": "Economize até 20% no plano anual",
    "mais_escolhido": "Mais escolhido",
    "descricao_padrao": "Tudo o que seu negócio precisa para crescer.",
    "por_mes": "por mês",
    "por_ano": "por ano (equivale a R$ {mensal}/mês)",
    "botao": "Testar o {plano} grátis →",
    "teste": "12 dias grátis · sem cartão",
}

# Itens que aparecem em todos os cartões de plano. Os números vêm do cadastro do plano (/admin/planos).
PLANO_RECURSOS = {
    "agenda": "Agenda online 24h com link próprio",
    "lucro": "Controle de custos e lucro por serviço",
    "usuarios": "Até {n} profissionais/usuários",
    "servicos": "{n} serviços no catálogo",
    "servicos_ilimitados": "Serviços ilimitados",
    "historico": "{n} meses de histórico nos relatórios",
    "fotos": "Aba “Sobre” com até {n} fotos",
    "sem_fotos": "Aba “Sobre” com galeria de fotos",
    "lembretes": "Lembretes por e-mail aos clientes",
    "relatorios_avancados": "Relatórios avançados de faturamento",
    "personalizacao": "Personalização avançada (logo e cores)",
    "equipe": "Agenda e comissão por profissional",
    "espera_pacotes": "Lista de espera, pacotes e avaliações",
    "dados": "Baixar todos os seus dados quando quiser",
    "gerente": "Função de gerente na equipe",
    "google_agenda": "Sincronização com Google Agenda",
    "exportacao": "CSV pronto para o contador",
    "dominio": "Domínio próprio",
}

# ---------------------------------------------------------------- Avaliações
AVALIACOES = {
    "etiqueta": "Avaliações dos contratantes",
    "titulo": "Quem usa, recomenda",
    "texto_sem_media": "Avaliações reais, feitas apenas por quem é ou já foi cliente do sistema.",
    "vazio_titulo": "Ainda não há avaliações",
    "vazio_texto": "Se você já é cliente, seja o primeiro a avaliar.",
    "form_titulo": "Avalie o MeuAgendamento",
    "form_texto": "Exclusivo para contratantes. O nome do seu negócio aparece na avaliação; seus dados de acesso, não.",
    "nota": "Sua nota *",
    "nota_dica": "Clique ou arraste sobre as estrelas (meia estrela = 0,5).",
    "comentario": "Comentário *",
    "comentario_placeholder": "Conte como o sistema ajudou o seu negócio...",
    "botao": "Enviar avaliação",
    "login_texto": "Para avaliar, entre com a conta do seu salão. Só contratantes conseguem publicar — assim ninguém avalia no seu nome.",
    "login_botao": "Entrar para avaliar",
}

# ---------------------------------------------------------------- Perguntas frequentes
FAQ_TITULO = "Perguntas frequentes"
FAQ = [
    {"pergunta": "Como funciona o teste grátis?", "resposta": "Você faz o cadastro, confirma o e-mail e usa tudo do plano escolhido por 12 dias, sem cartão. Faltando 5 dias para acabar, enviamos por e-mail o Pix para continuar. Se não pagar, nada é cobrado — o acesso só é pausado."},
    {"pergunta": "Como funciona o pagamento?", "resposta": "Por Pix, mensal ou anual. Avisamos por e-mail antes de cada vencimento. Se atrasar, você tem 7 dias de tolerância antes do acesso ser suspenso — e nenhum dado é apagado."},
    {"pergunta": "Posso colocar minha equipe?", "resposta": "Sim. Você convida cada pessoa por e-mail e escolhe a função: o funcionário vê só a própria agenda e os próprios ganhos; o gerente (Pro e Premium) organiza agenda e comissões."},
    {"pergunta": "Serve para o meu tipo de negócio?", "resposta": "Sim, se você atende com hora marcada. Salões, barbearias, manicures, clínicas de estética, designers de sobrancelha, massoterapeutas, estúdios de tatuagem, pet shops e muitos outros."},
    {"pergunta": "Posso mudar de plano depois?", "resposta": "Sim. Você pode fazer upgrade a qualquer momento, conforme sua equipe e sua clientela crescem."},
    {"pergunta": "Preciso instalar algum programa?", "resposta": "Não. Funciona 100% online, no computador, no tablet ou no celular, para você e para seus clientes."},
    {"pergunta": "Existe taxa de cancelamento?", "resposta": "Não há fidelidade nem multa. Você pode cancelar quando quiser."},
    {
        "pergunta": "E os meus dados?",
        "resposta": "Os dados ficam armazenados com segurança e são usados apenas para o funcionamento do sistema, conforme a LGPD.",
        "link_texto": "Veja os Termos de Uso e a Política de Privacidade",
        "link_url": "/termos",
    },
]

# ---------------------------------------------------------------- Chamada final e rodapé
CTA_FINAL = {
    "titulo": "Pronto para organizar sua agenda?",
    "texto": "Cadastre seu negócio em poucos minutos e use grátis por 12 dias.",
    "botao": "Começar meu teste grátis →",
}

RODAPE = {
    "copyright": "© 2026 MeuAgendamento — Todos os direitos reservados.",
    "termos": "Termos de Uso e Privacidade (LGPD)",
    "area_cliente": "Área do cliente",
}
