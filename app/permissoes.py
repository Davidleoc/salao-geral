"""
O QUE CADA FUNÇÃO DA EQUIPE PODE FAZER — edite aqui para mudar as regras.

  Dono         → tudo, inclusive mudar funções, assinatura, baixar dados e encerrar a conta
  Gerente      → organiza agenda, clientes, serviços, comissões e convites (não disponível no plano Básico)
  Funcionário  → só a própria agenda e os próprios ganhos

Uso nas rotas:      tenant.exigir("servicos.editar")
Uso nos templates:  {% if pode('relatorios.ver') %} ... {% endif %}
"""

PERMISSOES_DESCRICAO = {
    "painel.financeiro": "Ver faturamento e lucro do salão no painel",
    "agenda.todos": "Ver e organizar a agenda de todos os profissionais",
    "agenda.propria": "Ver e organizar a própria agenda",
    "clientes.ver": "Ver a lista e as fichas de clientes",
    "clientes.editar": "Cadastrar e editar clientes",
    "servicos.editar": "Cadastrar e editar serviços, preços e custos",
    "relatorios.ver": "Ver relatórios de faturamento e lucro",
    "relatorios.exportar": "Exportar CSV para o contador (plano Premium)",
    "comissoes.gerenciar": "Definir comissões e ver o relatório de comissões",
    "equipe.ver": "Ver a equipe",
    "equipe.convidar": "Convidar pessoas para a equipe",
    "equipe.papeis": "Mudar funções e remover pessoas da equipe",
    "configuracoes.editar": "Editar dados do salão, horários, página pública e avaliações",
    "assinatura.gerenciar": "Assinatura, documento fiscal, baixar dados e encerrar a conta",
    "pacotes.gerenciar": "Criar e vender pacotes e assinaturas de clientes",
    "lista_espera.ver": "Ver a lista de espera",
    "avaliacoes.ver": "Ver as avaliações dos clientes",
    "ganhos.proprios": "Ver os próprios atendimentos e comissões",
}

TODAS = set(PERMISSOES_DESCRICAO)

PERMISSOES = {
    "DONO": TODAS,
    "GERENTE": TODAS - {"equipe.papeis", "assinatura.gerenciar"},
    "FUNCIONARIO": {"agenda.propria", "ganhos.proprios"},
}

ROTULOS = {"DONO": "Dono", "GERENTE": "Gerente", "FUNCIONARIO": "Funcionário", "ADMIN": "Administrador"}

# Quem cada função pode convidar
PODE_CONVIDAR = {"DONO": ["GERENTE", "FUNCIONARIO"], "GERENTE": ["FUNCIONARIO"]}


class SemPermissao(Exception):
    def __init__(self, mensagem: str = "Você não tem permissão para acessar esta área."):
        self.mensagem = mensagem
        super().__init__(mensagem)


def papel_de(usuario) -> str:
    return getattr(usuario.role, "value", str(usuario.role))


def pode(usuario, permissao: str) -> bool:
    return permissao in PERMISSOES.get(papel_de(usuario), set())
