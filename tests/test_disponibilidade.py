import pytest
from datetime import date, time
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from decimal import Decimal

from app.database import Base
from app.models.salao import Salao
from app.models.horario import HorarioFuncionamento, BloqueioHorario
from app.models.servico import Servico
from app.models.agendamento import Agendamento, StatusAgendamento
from app.models.cliente import Cliente
from app.services.disponibilidade_service import calcular_disponibilidade

# Banco em memória para os testes
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture()
def db():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)

def test_motor_disponibilidade(db):
    # 1. Setup Básico
    salao = Salao(nome="Salão Teste", slug="salao-teste", email_principal="a@a.com")
    db.add(salao)
    db.commit()
    
    # 2. Configura serviço: 60 minutos
    servico = Servico(salao_id=salao.id, nome="Corte", preco=Decimal("50.0"), duracao_minutos=60)
    db.add(servico)
    db.commit()

    data_teste = date(2026, 10, 15) # Quinta-feira (weekday=3)
    
    # 3. Regra de Horário: Quinta, 09:00 às 12:00
    horario = HorarioFuncionamento(
        salao_id=salao.id,
        dia_semana=3, 
        ativo=True,
        hora_abertura=time(9, 0),
        hora_fechamento=time(12, 0),
        intervalo_minutos=30
    )
    db.add(horario)
    db.commit()

    # TESTE 1: Sem agendamentos. Intervalo de 30, serviço de 60.
    # Possibilidades teóricas de inicio: 09:00, 09:30, 10:00, 10:30, 11:00, 11:30
    # Como o serviço dura 60m e fecha as 12:00, o último slot possível é 11:00.
    # Resultado esperado: 09:00, 09:30, 10:00, 10:30, 11:00
    disp_1 = calcular_disponibilidade(db, salao.id, data_teste, servico)
    assert len(disp_1) == 5
    assert time(11, 0) in disp_1
    assert time(11, 30) not in disp_1 # Terminaria 12:30 (além do fechamento)

    # 4. Adiciona Pausa: 10:00 às 11:00
    horario.pausa_inicio = time(10, 0)
    horario.pausa_fim = time(11, 0)
    db.commit()

    # TESTE 2: Com pausa.
    # 09:00 - termina 10:00 (Pode, encosta na pausa mas não cruza)
    # 09:30 - termina 10:30 (Cruza pausa -> NO)
    # 10:00 - na pausa -> NO
    # 10:30 - na pausa -> NO
    # 11:00 - termina 12:00 (Pode, pós pausa e fecha as 12:00)
    disp_2 = calcular_disponibilidade(db, salao.id, data_teste, servico)
    assert len(disp_2) == 2
    assert time(9, 0) in disp_2
    assert time(11, 0) in disp_2

    # 5. Adiciona um Agendamento que ocupa das 11:00 às 12:00
    cliente = Cliente(salao_id=salao.id, nome="Cliente Teste", telefone="111")
    db.add(cliente)
    db.commit()
    
    ag = Agendamento(
        salao_id=salao.id,
        cliente_id=cliente.id,
        servico_id=servico.id,
        data=data_teste,
        hora_inicio=time(11, 0),
        hora_fim=time(12, 0),
        valor=Decimal("50.0"),
        status=StatusAgendamento.AGENDADO
    )
    db.add(ag)
    db.commit()

    # TESTE 3: Com agendamento.
    # O slot das 11:00 agora está ocupado.
    # Resta apenas 09:00.
    disp_3 = calcular_disponibilidade(db, salao.id, data_teste, servico)
    assert len(disp_3) == 1
    assert time(9, 0) in disp_3

    # TESTE 4: E se o agendamento for CANCELADO? O horário volta!
    ag.status = StatusAgendamento.CANCELADO_PELO_SALAO
    db.commit()
    
    disp_4 = calcular_disponibilidade(db, salao.id, data_teste, servico)
    assert len(disp_4) == 2
    assert time(11, 0) in disp_4
