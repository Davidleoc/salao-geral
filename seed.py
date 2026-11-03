"""
Script de Seed inicial do banco de dados:
- Cria os 3 Planos padrão (Básico, Pro, Premium) exatamente conforme especificação do projeto
- Cria o Super Admin inicial do SaaS (/admin)
- Cria um Salão de demonstração para testes rápidos (opcional)
"""

from decimal import Decimal
from app.database import SessionLocal
from app.models.plano import Plano
from app.models.usuario import Usuario, RoleUsuario
from app.models.salao import Salao
from app.models.assinatura import Assinatura, StatusAssinatura, Periodicidade
from app.models.horario import HorarioFuncionamento
from app.models.servico import Servico
from app.security import hash_senha
from datetime import time, date

def seed():
    db = SessionLocal()
    try:
        # 1. Cria os Planos se não existirem
        if db.query(Plano).count() == 0:
            planos = [
                Plano(
                    nome="Básico",
                    descricao="Ideal para profissionais autônomos e pequenos estúdios começando.",
                    preco_mensal=Decimal("49.90"),
                    preco_anual=Decimal("479.00"),
                    max_usuarios=2,
                    max_servicos=10,
                    max_emails=2,
                    historico_meses=2,
                    max_fotos=0,
                    exportacao=False,
                    lembretes=False,
                    personalizacao_avancada=False,
                    relatorios_avancados=False,
                    dominio_personalizado=False,
                    ativo=True
                ),
                Plano(
                    nome="Pro",
                    descricao="O plano mais popular para salões em expansão que querem automação completa.",
                    preco_mensal=Decimal("89.90"),
                    preco_anual=Decimal("863.00"),
                    max_usuarios=4,
                    max_servicos=30,
                    max_emails=3,
                    historico_meses=6,
                    max_fotos=5,
                    exportacao=False,
                    lembretes=True,
                    personalizacao_avancada=True,
                    relatorios_avancados=True,
                    dominio_personalizado=False,
                    ativo=True
                ),
                Plano(
                    nome="Premium",
                    descricao="Recursos ilimitados, relatórios avançados e exportação de dados.",
                    preco_mensal=Decimal("149.90"),
                    preco_anual=Decimal("1439.00"),
                    max_usuarios=10,
                    max_servicos=None, # ilimitado
                    max_emails=5,
                    historico_meses=12,
                    max_fotos=10,
                    exportacao=True,
                    lembretes=True,
                    personalizacao_avancada=True,
                    relatorios_avancados=True,
                    dominio_personalizado=True,
                    ativo=True
                ),
            ]
            db.add_all(planos)
            db.commit()
            print("✓ 3 Planos criados com sucesso!")

        # 2. Cria o Super Usuário Admin do SaaS
        admin_email = "admin@seudominio.com"
        admin_user = db.query(Usuario).filter(Usuario.email == admin_email).first()
        if not admin_user:
            admin = Usuario(
                nome="Administrador Geral",
                email=admin_email,
                senha_hash=hash_senha("admin123456"),
                role=RoleUsuario.ADMIN,
                ativo=True,
                email_verificado=True
            )
            db.add(admin)
            db.commit()
            print("✓ Super Admin criado! Login: admin@seudominio.com / Senha: admin123456")

        # 3. Cria Salão de demonstração (Studio Bella)
        demo_salao = db.query(Salao).filter(Salao.slug == "studio-bella").first()
        if not demo_salao:
            salao = Salao(
                nome="Studio Bella",
                slug="studio-bella",
                email_principal="contato@studiobella.com",
                telefone="(11) 99999-8888",
                whatsapp="11999998888",
                endereco="Av. Paulista, 1000 - Sala 42",
                cidade="São Paulo",
                estado="SP",
                cor_principal="#6366f1",
                cor_secundaria="#a855f7",
                ativo=True
            )
            db.add(salao)
            db.flush()

            # Cria Dono do Salão
            dono = Usuario(
                salao_id=salao.id,
                nome="Maria Bella",
                email="dono@studiobella.com",
                senha_hash=hash_senha("senha123456"),
                role=RoleUsuario.DONO,
                ativo=True,
                email_verificado=True
            )
            db.add(dono)

            # Assinatura Pro
            plano_pro = db.query(Plano).filter(Plano.nome == "Pro").first()
            if plano_pro:
                assinatura = Assinatura(
                    salao_id=salao.id,
                    plano_id=plano_pro.id,
                    periodicidade=Periodicidade.MENSAL,
                    status=StatusAssinatura.ATIVO,
                    valor_cobrado=plano_pro.preco_mensal,
                    data_inicio=date.today()
                )
                db.add(assinatura)

            # Horários de funcionamento (Seg a Sáb: 09:00 - 18:00, almoço 12:00 - 13:00)
            for dia in range(6):  # 0=Segunda ... 5=Sábado
                h = HorarioFuncionamento(
                    salao_id=salao.id,
                    dia_semana=dia,
                    ativo=True,
                    hora_abertura=time(9, 0),
                    hora_fechamento=time(18, 0),
                    intervalo_minutos=30,
                    pausa_inicio=time(12, 0),
                    pausa_fim=time(13, 0)
                )
                db.add(h)

            # Serviços iniciais
            servicos = [
                Servico(salao_id=salao.id, nome="Manicure Tradicional", preco=Decimal("45.00"), duracao_minutos=45, ativo=True),
                Servico(salao_id=salao.id, nome="Pedicure Completa", preco=Decimal("55.00"), duracao_minutos=60, ativo=True),
                Servico(salao_id=salao.id, nome="Design de Sobrancelhas", preco=Decimal("40.00"), duracao_minutos=30, ativo=True),
                Servico(salao_id=salao.id, nome="Corte Feminino & Escova", preco=Decimal("90.00"), duracao_minutos=60, ativo=True),
            ]
            db.add_all(servicos)
            db.commit()
            print("✓ Salão Demo 'Studio Bella' criado! Acesse: http://localhost:9080/studio-bella")
            print("✓ Login do Dono: dono@studiobella.com / Senha: senha123456")

    finally:
        db.close()

if __name__ == "__main__":
    seed()
