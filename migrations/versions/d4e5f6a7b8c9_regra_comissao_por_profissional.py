"""Regra de comissão por profissional: base (valor/lucro) e escopo (próprios/salão)

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-10-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Quem já tem comissão continua igual: % sobre o valor do que atendeu
    with op.batch_alter_table("usuarios") as batch:
        batch.add_column(sa.Column("comissao_base", sa.String(10), nullable=False, server_default="VALOR"))
        batch.add_column(sa.Column("comissao_escopo", sa.String(10), nullable=False, server_default="PROPRIOS"))


def downgrade() -> None:
    with op.batch_alter_table("usuarios") as batch:
        batch.drop_column("comissao_escopo")
        batch.drop_column("comissao_base")
