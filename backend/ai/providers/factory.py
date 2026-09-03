from ..models import AIIntegration
from .base import AIProviderError
from .openai_compat import OpenAICompatProvider

# Provedores com API no formato OpenAI. Um provedor com payload próprio entra
# aqui com a sua própria classe.
PROVIDERS = {
    AIIntegration.Provider.DEEPSEEK: OpenAICompatProvider,
    AIIntegration.Provider.OPENAI: OpenAICompatProvider,
}


def get_provider():
    integration = AIIntegration.objects.filter(is_active=True).first()
    if integration is None:
        raise AIProviderError(
            "Nenhuma integração de IA configurada. Peça ao administrador para "
            "configurar em Integrações."
        )
    cls = PROVIDERS.get(integration.provider)
    if cls is None:
        raise AIProviderError(f"Provedor {integration.provider} ainda não suportado.")
    return cls(integration)
