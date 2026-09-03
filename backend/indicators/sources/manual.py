from .base import BaseSource


class ManualSource(BaseSource):
    type = "manual"

    def test(self):
        return True, "Lançamento manual não requer conexão."

    def collect(self, indicator, period):
        return None
