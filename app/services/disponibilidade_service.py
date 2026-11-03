"""
Motor de Disponibilidade (Fase 8)

Calcula os horários disponíveis para agendamento.
Recebe:
  - salao_id
  - data (Date)
  - servico (com sua duracao_minutos)
  - profissional_id (opcional)

Retorna:
  - Lista de horários de início (time) disponíveis.
"""

from datetime import date, time, datetime, timedelta
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.horario import HorarioFuncionamento, BloqueioHorario
from app.models.agendamento import Agendamento, StatusAgendamento
from app.models.servico import Servico


def _time_to_datetime(d: date, t: time) -> datetime:
    return datetime.combine(d, t)


def _gerar_slots_possiveis(d: date, hora_inicio: time, hora_fim: time, intervalo_minutos: int) -> List[datetime]:
    """Gera todos os horários entre hora_inicio e hora_fim pulando de intervalo em intervalo."""
    slots = []
    atual = _time_to_datetime(d, hora_inicio)
    fim = _time_to_datetime(d, hora_fim)
    
    passo = timedelta(minutes=intervalo_minutos)
    
    while atual < fim:
        slots.append(atual)
        atual += passo
        
    return slots


def calcular_disponibilidade(
    db: Session,
    salao_id: int,
    data_alvo: date,
    servico: Servico,
    profissional_id: Optional[int] = None
) -> List[time]:
    
    # 1. Busca a regra de horário de funcionamento para o dia da semana
    dia_semana = data_alvo.weekday() # 0 = Segunda, 6 = Domingo
    
    # Primeiro tenta buscar regra específica do profissional
    horario_regra = None
    if profissional_id:
        horario_regra = db.query(HorarioFuncionamento).filter(
            HorarioFuncionamento.salao_id == salao_id,
            HorarioFuncionamento.profissional_id == profissional_id,
            HorarioFuncionamento.dia_semana == dia_semana
        ).first()
        
    # Se não tem regra específica, pega a regra geral do salão
    if not horario_regra:
        horario_regra = db.query(HorarioFuncionamento).filter(
            HorarioFuncionamento.salao_id == salao_id,
            HorarioFuncionamento.profissional_id == None,
            HorarioFuncionamento.dia_semana == dia_semana
        ).first()

    # Se não tem regra ou está inativo no dia, retorna vazio
    if not horario_regra or not horario_regra.ativo:
        return []

    # 2. Busca bloqueios de calendário para o dia (Feriados, etc)
    # Bloqueios do salão inteiro OU bloqueios específicos do profissional
    query_bloqueios = db.query(BloqueioHorario).filter(
        BloqueioHorario.salao_id == salao_id,
        BloqueioHorario.data == data_alvo
    )
    if profissional_id:
        query_bloqueios = query_bloqueios.filter(
            (BloqueioHorario.profissional_id == None) | (BloqueioHorario.profissional_id == profissional_id)
        )
    else:
        query_bloqueios = query_bloqueios.filter(BloqueioHorario.profissional_id == None)
        
    bloqueios = query_bloqueios.all()
    
    # Se há um bloqueio de dia inteiro, retorna vazio
    for b in bloqueios:
        if b.dia_inteiro:
            return []

    # 3. Busca agendamentos existentes no dia que ocupam horário
    query_agendamentos = db.query(Agendamento).filter(
        Agendamento.salao_id == salao_id,
        Agendamento.data == data_alvo,
        Agendamento.status.notin_([
            StatusAgendamento.CANCELADO_PELO_CLIENTE,
            StatusAgendamento.CANCELADO_PELO_SALAO
        ])
    )
    if profissional_id:
        # Agendamentos antigos sem profissional definido bloqueiam todos (evita encaixe duplo)
        query_agendamentos = query_agendamentos.filter(
            (Agendamento.profissional_id == profissional_id) | (Agendamento.profissional_id == None)  # noqa: E711
        )
    agendamentos_ocupados = query_agendamentos.all()

    # 4. Gera a grade de horários teórica (ignorando ocupações por enquanto)
    slots = _gerar_slots_possiveis(
        data_alvo, 
        horario_regra.hora_abertura, 
        horario_regra.hora_fechamento, 
        horario_regra.intervalo_minutos
    )
    
    # Duração do serviço que o cliente quer agendar
    duracao = timedelta(minutes=servico.duracao_minutos)
    
    horarios_disponiveis = []
    
    for slot_inicio in slots:
        slot_fim = slot_inicio + duracao
        
        # 4.1 Verifica se o serviço termina depois da hora de fechamento
        hora_fechamento_dt = _time_to_datetime(data_alvo, horario_regra.hora_fechamento)
        if slot_fim > hora_fechamento_dt:
            continue
            
        # 4.2 Verifica intersecção com a pausa de almoço
        if horario_regra.pausa_inicio and horario_regra.pausa_fim:
            pausa_inicio_dt = _time_to_datetime(data_alvo, horario_regra.pausa_inicio)
            pausa_fim_dt = _time_to_datetime(data_alvo, horario_regra.pausa_fim)
            
            # Tem sobreposição se: inicio_servico < fim_pausa E fim_servico > inicio_pausa
            if slot_inicio < pausa_fim_dt and slot_fim > pausa_inicio_dt:
                continue

        # 4.3 Verifica intersecção com bloqueios parciais do dia
        conflito_bloqueio = False
        for b in bloqueios:
            if b.hora_inicio and b.hora_fim:
                b_inicio_dt = _time_to_datetime(data_alvo, b.hora_inicio)
                b_fim_dt = _time_to_datetime(data_alvo, b.hora_fim)
                if slot_inicio < b_fim_dt and slot_fim > b_inicio_dt:
                    conflito_bloqueio = True
                    break
        if conflito_bloqueio:
            continue
            
        # 4.4 Verifica intersecção com outros agendamentos
        conflito_agendamento = False
        for ag in agendamentos_ocupados:
            ag_inicio_dt = _time_to_datetime(data_alvo, ag.hora_inicio)
            ag_fim_dt = _time_to_datetime(data_alvo, ag.hora_fim)
            if slot_inicio < ag_fim_dt and slot_fim > ag_inicio_dt:
                conflito_agendamento = True
                break
                
        if conflito_agendamento:
            continue
            
        # Se passou em todas as verificações, o slot está livre!
        horarios_disponiveis.append(slot_inicio.time())

    return horarios_disponiveis


# ---------------------------------------------------------------------------
# Agenda por profissional
# ---------------------------------------------------------------------------
def profissionais_que_atendem(db: Session, salao_id: int):
    """Pessoas da equipe que aparecem para o cliente escolher (ativas e com 'atende clientes')."""
    from app.models.usuario import Usuario, RoleUsuario
    return (db.query(Usuario)
            .filter(Usuario.salao_id == salao_id, Usuario.ativo == True,  # noqa: E712
                    Usuario.atende_clientes == True, Usuario.role != RoleUsuario.ADMIN)  # noqa: E712
            .order_by(Usuario.nome).all())


def horarios_livres(db: Session, salao_id: int, data_alvo: date, servico: Servico,
                    profissional_id: Optional[int] = None) -> List[tuple]:
    """
    Lista de (horário, id do profissional livre nesse horário).
    - Com profissional_id: só os horários dele.
    - Sem (cliente escolheu "qualquer profissional"): junta os horários de todos;
      em cada horário fica o primeiro profissional livre (por ordem alfabética).
    - Salão sem ninguém marcado como "atende clientes": comportamento antigo (uma agenda só).
    """
    if profissional_id:
        return [(h, profissional_id) for h in calcular_disponibilidade(db, salao_id, data_alvo, servico, profissional_id)]
    profissionais = profissionais_que_atendem(db, salao_id)
    if not profissionais:
        return [(h, None) for h in calcular_disponibilidade(db, salao_id, data_alvo, servico)]
    livres: dict = {}
    for prof in profissionais:
        for h in calcular_disponibilidade(db, salao_id, data_alvo, servico, prof.id):
            livres.setdefault(h, prof.id)
    return sorted(livres.items())


def conflito(db: Session, salao_id: int, data_alvo: date, inicio: time, fim: time,
             profissional_id: Optional[int], ignorar_id: Optional[int] = None) -> bool:
    """True se o horário bate com outro agendamento ativo do mesmo profissional."""
    q = db.query(Agendamento).filter(
        Agendamento.salao_id == salao_id, Agendamento.data == data_alvo,
        Agendamento.status.notin_([StatusAgendamento.CANCELADO_PELO_CLIENTE, StatusAgendamento.CANCELADO_PELO_SALAO]),
        Agendamento.hora_inicio < fim, Agendamento.hora_fim > inicio,
    )
    if profissional_id:
        q = q.filter((Agendamento.profissional_id == profissional_id) | (Agendamento.profissional_id == None))  # noqa: E711
    if ignorar_id:
        q = q.filter(Agendamento.id != ignorar_id)
    return db.query(q.exists()).scalar()
