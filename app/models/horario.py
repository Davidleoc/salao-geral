"""
Modelos: HorarioFuncionamento e BloqueioHorario

HorarioFuncionamento:
  Define os dias e horários de trabalho de cada profissional (ou do salão inteiro).
  dia_semana: 0=Segunda, 1=Terça, ..., 6=Domingo

BloqueioHorario:
  Exceções — dias ou períodos em que o salão/profissional não atende.
  Exemplos:
    - 15/10 (dia inteiro): Feriado
    - 20/10 14:00–16:00: Compromisso

O motor de disponibilidade (disponibilidade_service.py) usa esses dois modelos
para calcular os horários livres de um profissional em uma data específica.
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Date, Time, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class HorarioFuncionamento(Base):
    __tablename__ = "horarios_funcionamento"

    id = Column(Integer, primary_key=True, index=True)
    salao_id = Column(Integer, ForeignKey("saloes.id"), nullable=False, index=True)

    # None = regra do salão inteiro; int = regra de um profissional específico
    profissional_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)

    dia_semana = Column(Integer, nullable=False)      # 0=Segunda ... 6=Domingo
    ativo = Column(Boolean, default=True)             # False = não atende neste dia

    hora_abertura = Column(Time, nullable=False)
    hora_fechamento = Column(Time, nullable=False)

    # Pausa (almoço, intervalo)
    pausa_inicio = Column(Time, nullable=True)
    pausa_fim = Column(Time, nullable=True)

    # Intervalo entre slots (minutos): 15, 30, 45, 60
    intervalo_minutos = Column(Integer, nullable=False, default=30)

    criado_em = Column(DateTime(timezone=True), server_default=func.now())
    atualizado_em = Column(DateTime(timezone=True), onupdate=func.now())

    # Relacionamentos
    salao = relationship("Salao", back_populates="horarios")
    profissional = relationship("Usuario", foreign_keys=[profissional_id])


class BloqueioHorario(Base):
    __tablename__ = "bloqueios_horario"

    id = Column(Integer, primary_key=True, index=True)
    salao_id = Column(Integer, ForeignKey("saloes.id"), nullable=False, index=True)
    profissional_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)

    data = Column(Date, nullable=False)
    dia_inteiro = Column(Boolean, default=False)

    # Preenchidos quando dia_inteiro=False
    hora_inicio = Column(Time, nullable=True)
    hora_fim = Column(Time, nullable=True)

    motivo = Column(Text, nullable=True)

    criado_em = Column(DateTime(timezone=True), server_default=func.now())

    # Relacionamentos
    salao = relationship("Salao", back_populates="bloqueios")
    profissional = relationship("Usuario", foreign_keys=[profissional_id])
