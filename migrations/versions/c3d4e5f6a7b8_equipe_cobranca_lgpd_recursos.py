"""equipe, cobrança automática, LGPD, notificações, lista de espera, pacotes, avaliações

Revision ID: c3d4e5f6a7b8
Revises: b7c1e2f3a4d5
Create Date: 2026-10-16 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b7c1e2f3a4d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

AGORA = sa.text('(CURRENT_TIMESTAMP)')

NOVOS_ENUMS = {
    "roleusuario": ["GERENTE"],
    "statusassinatura": ["TESTE", "EM_ATRASO"],
    "eventoseguranca": [
        "CONVITE_ENVIADO", "PAPEL_ALTERADO", "EMAIL_VERIFICADO", "SENHA_RESET_SOLICITADO",
        "SENHA_RESET_ENVIADO", "PAGAMENTO_CONFIRMADO", "ASSINATURA_ALTERADA", "SALAO_ALTERADO",
        "PLANO_ALTERADO", "ACESSO_SUPORTE", "DADOS_EXPORTADOS", "CONTA_ENCERRADA",
        "DADOS_ANONIMIZADOS", "LIMITE_EXCEDIDO",
    ],
}


def upgrade() -> None:
    bind = op.get_bind()

    # ---- PostgreSQL: novos valores nos tipos ENUM (no SQLite são texto livre)
    if bind.dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            for tipo, valores in NOVOS_ENUMS.items():
                for v in valores:
                    op.execute(f"ALTER TYPE {tipo} ADD VALUE IF NOT EXISTS '{v}'")

    # ---- Tabelas novas
    op.create_table(
        'pacotes',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('salao_id', sa.Integer(), sa.ForeignKey('saloes.id'), nullable=False),
        sa.Column('nome', sa.String(150), nullable=False),
        sa.Column('descricao', sa.Text(), nullable=True),
        sa.Column('tipo', sa.String(12), nullable=False, server_default='PACOTE'),
        sa.Column('servico_id', sa.Integer(), sa.ForeignKey('servicos.id'), nullable=True),
        sa.Column('quantidade_sessoes', sa.Integer(), nullable=False),
        sa.Column('preco', sa.Numeric(10, 2), nullable=False),
        sa.Column('validade_dias', sa.Integer(), nullable=False, server_default='90'),
        sa.Column('publico', sa.Boolean(), nullable=True, server_default=sa.true()),
        sa.Column('ativo', sa.Boolean(), nullable=True, server_default=sa.true()),
        sa.Column('criado_em', sa.DateTime(timezone=True), server_default=AGORA),
    )
    op.create_index('ix_pacotes_id', 'pacotes', ['id'])
    op.create_index('ix_pacotes_salao_id', 'pacotes', ['salao_id'])

    op.create_table(
        'pacotes_clientes',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('salao_id', sa.Integer(), sa.ForeignKey('saloes.id'), nullable=False),
        sa.Column('pacote_id', sa.Integer(), sa.ForeignKey('pacotes.id'), nullable=False),
        sa.Column('cliente_id', sa.Integer(), sa.ForeignKey('clientes.id'), nullable=False),
        sa.Column('sessoes_total', sa.Integer(), nullable=False),
        sa.Column('sessoes_usadas', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('valor_pago', sa.Numeric(10, 2), nullable=False),
        sa.Column('forma_pagamento', sa.String(12), nullable=True),
        sa.Column('inicio', sa.Date(), nullable=False),
        sa.Column('validade', sa.Date(), nullable=False),
        sa.Column('status', sa.String(12), nullable=False, server_default='ATIVO'),
        sa.Column('vendido_por_id', sa.Integer(), sa.ForeignKey('usuarios.id'), nullable=True),
        sa.Column('criado_em', sa.DateTime(timezone=True), server_default=AGORA),
    )
    op.create_index('ix_pacotes_clientes_id', 'pacotes_clientes', ['id'])
    op.create_index('ix_pacotes_clientes_salao_id', 'pacotes_clientes', ['salao_id'])
    op.create_index('ix_pacotes_clientes_cliente_id', 'pacotes_clientes', ['cliente_id'])

    op.create_table(
        'convites_equipe',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('salao_id', sa.Integer(), sa.ForeignKey('saloes.id'), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('papel', sa.String(20), nullable=False),
        sa.Column('token_hash', sa.String(64), nullable=False, unique=True),
        sa.Column('criado_por_id', sa.Integer(), sa.ForeignKey('usuarios.id'), nullable=True),
        sa.Column('criado_em', sa.DateTime(timezone=True), server_default=AGORA),
        sa.Column('expira_em', sa.DateTime(timezone=True), nullable=False),
        sa.Column('usado_em', sa.DateTime(timezone=True), nullable=True),
        sa.Column('usuario_criado_id', sa.Integer(), sa.ForeignKey('usuarios.id'), nullable=True),
        sa.Column('cancelado_em', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_convites_equipe_id', 'convites_equipe', ['id'])
    op.create_index('ix_convites_equipe_salao_id', 'convites_equipe', ['salao_id'])
    op.create_index('ix_convites_equipe_email', 'convites_equipe', ['email'])

    op.create_table(
        'notificacoes_painel',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('destino', sa.String(10), nullable=False, server_default='SALAO'),
        sa.Column('salao_id', sa.Integer(), sa.ForeignKey('saloes.id'), nullable=True),
        sa.Column('para_papeis', sa.String(60), nullable=True),
        sa.Column('usuario_id', sa.Integer(), sa.ForeignKey('usuarios.id'), nullable=True),
        sa.Column('autor_id', sa.Integer(), sa.ForeignKey('usuarios.id'), nullable=True),
        sa.Column('tipo', sa.String(40), nullable=False),
        sa.Column('titulo', sa.String(150), nullable=False),
        sa.Column('mensagem', sa.String(500), nullable=True),
        sa.Column('link', sa.String(300), nullable=True),
        sa.Column('criado_em', sa.DateTime(timezone=True), server_default=AGORA),
    )
    op.create_index('ix_notificacoes_painel_id', 'notificacoes_painel', ['id'])
    op.create_index('ix_notificacoes_painel_destino', 'notificacoes_painel', ['destino'])
    op.create_index('ix_notificacoes_painel_salao_id', 'notificacoes_painel', ['salao_id'])
    op.create_index('ix_notificacoes_painel_criado_em', 'notificacoes_painel', ['criado_em'])

    op.create_table(
        'envios_automaticos',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('chave', sa.String(200), nullable=False, unique=True),
        sa.Column('criado_em', sa.DateTime(timezone=True), server_default=AGORA),
    )
    op.create_index('ix_envios_automaticos_criado_em', 'envios_automaticos', ['criado_em'])

    op.create_table(
        'solicitacoes_senha',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('usuario_id', sa.Integer(), sa.ForeignKey('usuarios.id'), nullable=False),
        sa.Column('status', sa.String(12), nullable=False, server_default='PENDENTE'),
        sa.Column('ip', sa.String(45), nullable=True),
        sa.Column('criado_em', sa.DateTime(timezone=True), server_default=AGORA),
        sa.Column('atendido_em', sa.DateTime(timezone=True), nullable=True),
        sa.Column('atendido_por_id', sa.Integer(), sa.ForeignKey('usuarios.id'), nullable=True),
    )
    op.create_index('ix_solicitacoes_senha_id', 'solicitacoes_senha', ['id'])
    op.create_index('ix_solicitacoes_senha_usuario_id', 'solicitacoes_senha', ['usuario_id'])
    op.create_index('ix_solicitacoes_senha_status', 'solicitacoes_senha', ['status'])

    op.create_table(
        'lista_espera',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('salao_id', sa.Integer(), sa.ForeignKey('saloes.id'), nullable=False),
        sa.Column('servico_id', sa.Integer(), sa.ForeignKey('servicos.id'), nullable=False),
        sa.Column('profissional_id', sa.Integer(), sa.ForeignKey('usuarios.id'), nullable=True),
        sa.Column('data', sa.Date(), nullable=False),
        sa.Column('nome', sa.String(200), nullable=False),
        sa.Column('telefone', sa.String(20), nullable=False),
        sa.Column('email', sa.String(255), nullable=True),
        sa.Column('status', sa.String(12), nullable=False, server_default='AGUARDANDO'),
        sa.Column('criado_em', sa.DateTime(timezone=True), server_default=AGORA),
        sa.Column('avisado_em', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_lista_espera_id', 'lista_espera', ['id'])
    op.create_index('ix_lista_espera_salao_id', 'lista_espera', ['salao_id'])
    op.create_index('ix_lista_espera_data', 'lista_espera', ['data'])
    op.create_index('ix_lista_espera_status', 'lista_espera', ['status'])

    op.create_table(
        'avaliacoes_atendimento',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('salao_id', sa.Integer(), sa.ForeignKey('saloes.id'), nullable=False),
        sa.Column('agendamento_id', sa.Integer(), sa.ForeignKey('agendamentos.id'), nullable=False, unique=True),
        sa.Column('token_hash', sa.String(64), nullable=False, unique=True),
        sa.Column('nota', sa.Integer(), nullable=True),
        sa.Column('comentario', sa.Text(), nullable=True),
        sa.Column('criado_em', sa.DateTime(timezone=True), server_default=AGORA),
        sa.Column('respondido_em', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_avaliacoes_atendimento_id', 'avaliacoes_atendimento', ['id'])
    op.create_index('ix_avaliacoes_atendimento_salao_id', 'avaliacoes_atendimento', ['salao_id'])

    op.create_table(
        'pagamentos_assinatura',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('assinatura_id', sa.Integer(), sa.ForeignKey('assinaturas.id'), nullable=False),
        sa.Column('salao_id', sa.Integer(), sa.ForeignKey('saloes.id'), nullable=False),
        sa.Column('valor', sa.Numeric(10, 2), nullable=False),
        sa.Column('periodo_inicio', sa.Date(), nullable=False),
        sa.Column('periodo_fim', sa.Date(), nullable=False),
        sa.Column('forma', sa.String(20), nullable=True),
        sa.Column('confirmado_por_id', sa.Integer(), sa.ForeignKey('usuarios.id'), nullable=True),
        sa.Column('pago_em', sa.DateTime(timezone=True), server_default=AGORA),
    )
    op.create_index('ix_pagamentos_assinatura_id', 'pagamentos_assinatura', ['id'])
    op.create_index('ix_pagamentos_assinatura_assinatura_id', 'pagamentos_assinatura', ['assinatura_id'])
    op.create_index('ix_pagamentos_assinatura_salao_id', 'pagamentos_assinatura', ['salao_id'])
    op.create_index('ix_pagamentos_assinatura_pago_em', 'pagamentos_assinatura', ['pago_em'])

    # ---- Colunas novas em tabelas existentes
    with op.batch_alter_table('usuarios') as b:
        b.add_column(sa.Column('especialidade', sa.String(100), nullable=True))
        b.add_column(sa.Column('foto', sa.String(500), nullable=True))
        b.add_column(sa.Column('telefone', sa.String(20), nullable=True))
        b.add_column(sa.Column('atende_clientes', sa.Boolean(), nullable=True, server_default=sa.true()))
        b.add_column(sa.Column('comissao_percentual', sa.Numeric(5, 2), nullable=True))
        b.add_column(sa.Column('calendario_token', sa.String(64), nullable=True))
        b.add_column(sa.Column('ultima_notificacao_vista', sa.Integer(), nullable=False, server_default='0'))
        b.create_unique_constraint('uq_usuarios_calendario_token', ['calendario_token'])

    with op.batch_alter_table('saloes') as b:
        b.add_column(sa.Column('documento', sa.String(14), nullable=True))
        b.add_column(sa.Column('tipo_documento', sa.String(4), nullable=True))
        b.add_column(sa.Column('pedir_avaliacao', sa.Boolean(), nullable=True, server_default=sa.false()))
        b.add_column(sa.Column('link_avaliacao_google', sa.String(500), nullable=True))
        b.add_column(sa.Column('encerrado_em', sa.DateTime(timezone=True), nullable=True))
        b.add_column(sa.Column('exclusao_prevista_em', sa.DateTime(timezone=True), nullable=True))
        b.add_column(sa.Column('anonimizado_em', sa.DateTime(timezone=True), nullable=True))
        b.create_index('ix_saloes_documento', ['documento'])

    with op.batch_alter_table('planos') as b:
        b.add_column(sa.Column('permite_gerente', sa.Boolean(), nullable=True, server_default=sa.false()))
        b.add_column(sa.Column('sincronizacao_agenda', sa.Boolean(), nullable=True, server_default=sa.false()))

    with op.batch_alter_table('assinaturas') as b:
        b.add_column(sa.Column('cancelada_em', sa.DateTime(timezone=True), nullable=True))

    with op.batch_alter_table('agendamentos') as b:
        b.add_column(sa.Column('comissao_percentual', sa.Numeric(5, 2), nullable=True))
        b.add_column(sa.Column('pacote_cliente_id', sa.Integer(), nullable=True))
        b.create_foreign_key('fk_agendamentos_pacote_cliente', 'pacotes_clientes', ['pacote_cliente_id'], ['id'])

    # ---- Dados iniciais
    # Gerente e sincronização de agenda: só a partir do plano Pro
    op.execute("UPDATE planos SET permite_gerente = 1, sincronizacao_agenda = 1 WHERE lower(nome) IN ('pro', 'premium')"
               if bind.dialect.name == "sqlite" else
               "UPDATE planos SET permite_gerente = true, sincronizacao_agenda = true WHERE lower(nome) IN ('pro', 'premium')")
    # Contas que já existiam antes da confirmação de e-mail são consideradas verificadas
    op.execute("UPDATE usuarios SET email_verificado = " + ("1" if bind.dialect.name == "sqlite" else "true"))
    # Assinaturas antigas sem vencimento ganham um ciclo a partir de hoje (evita suspensão imediata)
    if bind.dialect.name == "sqlite":
        op.execute("UPDATE assinaturas SET data_fim = date('now', '+30 day') WHERE status = 'ATIVO' AND data_fim IS NULL")
    else:
        op.execute("UPDATE assinaturas SET data_fim = CURRENT_DATE + 30 WHERE status = 'ATIVO' AND data_fim IS NULL")

    # Cifra segredos de MFA que estavam em texto puro
    from app.security import cifrar
    linhas = bind.execute(sa.text("SELECT id, mfa_secret FROM usuarios WHERE mfa_secret IS NOT NULL AND mfa_secret NOT LIKE 'enc:%'")).fetchall()
    for uid, segredo in linhas:
        bind.execute(sa.text("UPDATE usuarios SET mfa_secret = :s WHERE id = :i"), {"s": cifrar(segredo), "i": uid})


def downgrade() -> None:
    with op.batch_alter_table('agendamentos') as b:
        b.drop_constraint('fk_agendamentos_pacote_cliente', type_='foreignkey')
        b.drop_column('pacote_cliente_id')
        b.drop_column('comissao_percentual')
    with op.batch_alter_table('assinaturas') as b:
        b.drop_column('cancelada_em')
    with op.batch_alter_table('planos') as b:
        b.drop_column('sincronizacao_agenda')
        b.drop_column('permite_gerente')
    with op.batch_alter_table('saloes') as b:
        b.drop_index('ix_saloes_documento')
        for c in ['anonimizado_em', 'exclusao_prevista_em', 'encerrado_em', 'link_avaliacao_google',
                  'pedir_avaliacao', 'tipo_documento', 'documento']:
            b.drop_column(c)
    with op.batch_alter_table('usuarios') as b:
        b.drop_constraint('uq_usuarios_calendario_token', type_='unique')
        for c in ['ultima_notificacao_vista', 'calendario_token', 'comissao_percentual', 'atende_clientes',
                  'telefone', 'foto', 'especialidade']:
            b.drop_column(c)
    for t in ['pagamentos_assinatura', 'avaliacoes_atendimento', 'lista_espera', 'solicitacoes_senha',
              'envios_automaticos', 'notificacoes_painel', 'convites_equipe', 'pacotes_clientes', 'pacotes']:
        op.drop_table(t)
