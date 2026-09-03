from dataclasses import dataclass


@dataclass
class AIResponse:
    content: str
    tokens_used: int = 0


class AIProviderError(Exception):
    pass


class AIProvider:
    def __init__(self, integration):
        self.integration = integration

    def chat(self, messages, **kwargs) -> AIResponse:
        raise NotImplementedError
