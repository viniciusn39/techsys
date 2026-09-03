import httpx

from .base import AIProvider, AIProviderError, AIResponse


class OpenAICompatProvider(AIProvider):
    """Cobre DeepSeek e OpenAI (API /chat/completions compatível)."""

    def chat(self, messages, **kwargs) -> AIResponse:
        api_key = self.integration.get_api_key()
        if not api_key:
            raise AIProviderError("API key não configurada na integração de IA.")

        payload = {
            "model": self.integration.model,
            "messages": messages,
            "temperature": float(self.integration.temperature),
            "max_tokens": self.integration.max_tokens,
        }
        payload.update(kwargs)

        try:
            response = httpx.post(
                f"{self.integration.base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
                timeout=90,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise AIProviderError(
                f"Provedor retornou {exc.response.status_code}: {exc.response.text[:300]}"
            ) from exc
        except httpx.HTTPError as exc:
            raise AIProviderError(f"Falha de conexão com o provedor: {exc}") from exc

        data = response.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise AIProviderError(f"Resposta inesperada do provedor: {str(data)[:300]}") from exc
        tokens = (data.get("usage") or {}).get("total_tokens", 0)
        return AIResponse(content=content, tokens_used=tokens)
