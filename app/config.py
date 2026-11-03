import logging
import secrets

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# Valores placeholder que NUNCA devem ser usados como chave real.
_SECRETS_INSEGUROS = {
    "supersecretkey",
    "supersecretkey_change_in_production",
    "change_in_production",
    "",
}


class Settings(BaseSettings):
    APP_NAME: str = "MeuAgendamento"
    APP_ENV: str = "development"
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/salao_saas"
    SECRET_KEY: str = "supersecretkey"
    EMAIL_API_KEY: str = ""
    EMAIL_FROM: str = "noreply@seudominio.com"
    ADMIN_EMAIL: str = "admin@seudominio.com"
    SESSION_EXPIRE_MINUTES: int = 60
    MAX_UPLOAD_MB: int = 5
    # MFA (segundo fator) temporariamente desligado enquanto em validação.
    # Ligue com MFA_ENABLED=true no .env quando quiser exigir o código TOTP.
    MFA_ENABLED: bool = False
    # Com MFA ligado: obriga o administrador do SaaS a configurar o MFA antes de usar o /admin
    MFA_ADMIN_OBRIGATORIO: bool = False
    # Chave para cifrar dados sensíveis no banco (segredo do MFA). Vazia = derivada do SECRET_KEY.
    CHAVE_CRIPTOGRAFIA: str = ""

    # Endereço público do sistema — usado nos links dos e-mails
    URL_BASE: str = "http://localhost:9080"

    # Envio de e-mails (SMTP). Sem SMTP_HOST, os e-mails só ficam registrados (log e /dev/emails).
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USUARIO: str = ""
    SMTP_SENHA: str = ""
    SMTP_TLS: bool = True

    # Tarefas automáticas (lembretes, cobrança, retenção LGPD) — rodam dentro do servidor
    TAREFAS_AUTOMATICAS: bool = True
    TAREFAS_INTERVALO_MINUTOS: int = 10
    LEMBRETE_HORAS_ANTES: int = 24

    # Assinatura do salão
    DIAS_TESTE: int = 12                 # teste grátis
    DIAS_AVISO_VENCIMENTO: int = 5       # começa a avisar (um e-mail por dia) X dias antes
    DIAS_TOLERANCIA_ATRASO: int = 7      # suspende depois de X dias em atraso

    # Recebimento das assinaturas por Pix (gera o "Pix copia e cola" do e-mail de cobrança)
    PIX_CHAVE: str = ""
    PIX_NOME_RECEBEDOR: str = "MeuAgendamento"
    PIX_CIDADE: str = "SAO PAULO"

    # Equipe
    CONVITE_VALIDADE_DIAS: int = 7

    # LGPD — retenção de dados
    RETENCAO_LOGS_DIAS: int = 180                    # Marco Civil: mínimo de 6 meses
    RETENCAO_CLIENTE_INATIVO_MESES: int = 24         # anonimiza clientes sem atendimento há X meses
    PRAZO_EXCLUSAO_CONTA_DIAS: int = 30              # dados ficam disponíveis para baixar após encerrar

    # Atrás de proxy/CDN (nginx, Cloudflare): use o IP do cabeçalho X-Forwarded-For nos limites
    CONFIAR_PROXY: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() in ("production", "prod")

    @property
    def cookie_secure(self) -> bool:
        """Cookies só com secure=True em produção (onde há HTTPS)."""
        return self.is_production

    def _validar_secret(self) -> None:
        """
        A chave assina os JWT de sessão. Se for um placeholder conhecido,
        qualquer pessoa consegue forjar um token de admin.
          - Em produção: aborta a inicialização.
          - Em desenvolvimento: gera uma chave aleatória para esta execução
            (as sessões expiram a cada reinício, o que é aceitável localmente).
        """
        if self.SECRET_KEY in _SECRETS_INSEGUROS or len(self.SECRET_KEY) < 32:
            if self.is_production:
                raise RuntimeError(
                    "SECRET_KEY inseguro em produção. Defina SECRET_KEY no .env com um "
                    "valor aleatório forte, ex: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
                )
            self.SECRET_KEY = secrets.token_urlsafe(48)
            logger.warning(
                "SECRET_KEY inseguro: gerada uma chave aleatória temporária para esta "
                "execução de desenvolvimento. Defina SECRET_KEY no .env para manter as sessões."
            )


settings = Settings()
settings._validar_secret()
