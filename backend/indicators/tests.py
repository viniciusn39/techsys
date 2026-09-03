from datetime import date
from decimal import Decimal

from django.test import TestCase

from accounts.models import Tenant
from plans.models import Deviation

from .models import Indicator, IndicatorTarget, IndicatorValue
from .services import compute_ytd


class FarolTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="T", slug="t")

    def _make(self, polarity, aggregation=Indicator.Aggregation.SOMA):
        return Indicator.objects.create(
            tenant=self.tenant, code=f"K{polarity[:3]}{aggregation[:3]}",
            name="KPI", polarity=polarity, aggregation=aggregation,
        )

    def _lancar(self, ind, month, target, value):
        period = date(2026, month, 1)
        IndicatorTarget.objects.create(indicator=ind, period=period, target_value=target)
        v = IndicatorValue.objects.create(indicator=ind, period=period, value=value)
        return v

    def test_maior_melhor_verde_amarelo_vermelho(self):
        ind = self._make(Indicator.Polarity.MAIOR_MELHOR)
        self.assertEqual(self._lancar(ind, 1, 100, 110).status, "verde")
        self.assertEqual(self._lancar(ind, 2, 100, 95).status, "amarelo")
        self.assertEqual(self._lancar(ind, 3, 100, 80).status, "vermelho")

    def test_menor_melhor_inverte_atingimento(self):
        ind = self._make(Indicator.Polarity.MENOR_MELHOR)
        v = self._lancar(ind, 1, 100, 80)  # gastou menos que a meta
        self.assertEqual(v.status, "verde")
        self.assertEqual(v.achievement_pct, Decimal("125.00"))
        v2 = self._lancar(ind, 2, 100, 130)  # estourou a meta
        self.assertEqual(v2.status, "vermelho")

    def test_sem_meta(self):
        ind = self._make(Indicator.Polarity.MAIOR_MELHOR)
        v = IndicatorValue.objects.create(indicator=ind, period=date(2026, 1, 1), value=50)
        self.assertEqual(v.status, "sem_meta")
        self.assertIsNone(v.achievement_pct)

    def test_valor_vermelho_cria_desvio_e_correcao_remove(self):
        ind = self._make(Indicator.Polarity.MAIOR_MELHOR)
        v = self._lancar(ind, 1, 100, 50)
        self.assertTrue(Deviation.objects.filter(indicator_value=v).exists())
        v.value = 120
        v.save()
        self.assertFalse(Deviation.objects.filter(indicator_value=v).exists())

    def test_ytd_soma(self):
        ind = self._make(Indicator.Polarity.MAIOR_MELHOR)
        self._lancar(ind, 1, 100, 110)
        self._lancar(ind, 2, 100, 90)
        ytd = compute_ytd(ind, 2026)
        self.assertEqual(ytd["value"], Decimal("200"))
        self.assertEqual(ytd["target"], Decimal("200"))
        self.assertEqual(ytd["achievement_pct"], Decimal("100.00"))

    def test_ytd_media(self):
        ind = self._make(Indicator.Polarity.MAIOR_MELHOR, Indicator.Aggregation.MEDIA)
        self._lancar(ind, 1, 100, 80)
        self._lancar(ind, 2, 100, 120)
        ytd = compute_ytd(ind, 2026)
        self.assertEqual(ytd["value"], Decimal("100"))

    def test_ytd_ultimo(self):
        ind = self._make(Indicator.Polarity.MAIOR_MELHOR, Indicator.Aggregation.ULTIMO)
        self._lancar(ind, 1, 100, 80)
        self._lancar(ind, 2, 100, 120)
        ytd = compute_ytd(ind, 2026)
        self.assertEqual(ytd["value"], Decimal("120"))

    def test_recalculo_apos_mudanca_de_meta(self):
        ind = self._make(Indicator.Polarity.MAIOR_MELHOR)
        v = self._lancar(ind, 1, 100, 95)
        self.assertEqual(v.status, "amarelo")
        ind.targets.filter(period=date(2026, 1, 1)).update(target_value=90)
        v.save()
        self.assertEqual(v.status, "verde")
