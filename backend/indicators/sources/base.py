"""Ponto de extensão para coleta automática de valores de indicadores.

O agente conector de ERP será plugado aqui: basta criar uma classe que herda
BaseSource, implementar collect() e registrá-la no registry.
"""


class BaseSource:
    type = None

    def __init__(self, data_source):
        self.data_source = data_source
        self.config = data_source.config or {}

    def test(self):
        """Testa a conexão/configuração. Retorna (ok: bool, message: str)."""
        return True, "OK"

    def collect(self, indicator, period):
        """Coleta o valor do indicador no período. Retorna Decimal ou None."""
        raise NotImplementedError
