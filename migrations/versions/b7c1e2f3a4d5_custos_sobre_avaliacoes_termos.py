"""custos, aba sobre com fotos, avaliacoes e aceite de termos

Revision ID: b7c1e2f3a4d5
Revises: 9a33d2442938
Create Date: 2026-10-15 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7c1e2f3a4d5'
down_revision: Union[str, None] = '9a33d2442938'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Custo do serviço (opcional) e snapshot do custo no agendamento
    op.add_column('servicos', sa.Column('custo', sa.Numeric(10, 2), nullable=True))
    op.add_column('agendamentos', sa.Column('custo', sa.Numeric(10, 2), nullable=True))

    # Aba "Sobre" do salão
    op.add_column('saloes', sa.Column('sobre', sa.Text(), nullable=True))

    # Limite de fotos por plano
    op.add_column('planos', sa.Column('max_fotos', sa.Integer(), nullable=False, server_default='0'))
    op.execute("UPDATE planos SET max_fotos = 5 WHERE lower(nome) = 'pro'")
    op.execute("UPDATE planos SET max_fotos = 10 WHERE lower(nome) = 'premium'")

    # Aceite dos termos (LGPD)
    op.add_column('usuarios', sa.Column('termos_aceitos_em', sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        'fotos_salao',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('salao_id', sa.Integer(), nullable=False),
        sa.Column('caminho', sa.String(length=500), nullable=False),
        sa.Column('ordem', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('criado_em', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.ForeignKeyConstraint(['salao_id'], ['saloes.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_fotos_salao_id'), 'fotos_salao', ['id'], unique=False)
    op.create_index(op.f('ix_fotos_salao_salao_id'), 'fotos_salao', ['salao_id'], unique=False)

    op.create_table(
        'avaliacoes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('salao_id', sa.Integer(), nullable=False),
        sa.Column('nota', sa.Numeric(2, 1), nullable=False),
        sa.Column('comentario', sa.String(length=800), nullable=False),
        sa.Column('criado_em', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.Column('atualizado_em', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['salao_id'], ['saloes.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('salao_id'),
    )
    op.create_index(op.f('ix_avaliacoes_id'), 'avaliacoes', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_avaliacoes_id'), table_name='avaliacoes')
    op.drop_table('avaliacoes')
    op.drop_index(op.f('ix_fotos_salao_salao_id'), table_name='fotos_salao')
    op.drop_index(op.f('ix_fotos_salao_id'), table_name='fotos_salao')
    op.drop_table('fotos_salao')
    with op.batch_alter_table('usuarios') as batch:
        batch.drop_column('termos_aceitos_em')
    with op.batch_alter_table('planos') as batch:
        batch.drop_column('max_fotos')
    with op.batch_alter_table('saloes') as batch:
        batch.drop_column('sobre')
    with op.batch_alter_table('agendamentos') as batch:
        batch.drop_column('custo')
    with op.batch_alter_table('servicos') as batch:
        batch.drop_column('custo')
