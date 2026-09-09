from rest_framework.test import APITestCase

from .models import ActionPlan, Deviation




class KanbanTests(APITestCase):
    def setUp(self):
        from accounts.models import Tenant, User

        self.tenant = Tenant.objects.create(name="Acme", slug="acme-kanban")
        self.gestor = User.objects.create_user("k@acme.com", "x", first_name="Kai", tenant=self.tenant, role=User.Role.GESTOR)
        self.client.force_authenticate(self.gestor)
        self.plan = ActionPlan.objects.create(tenant=self.tenant, title="Plano", status=ActionPlan.Status.EM_ANDAMENTO)

    def test_bloqueio_prioridade_e_analise(self):
        r = self.client.post("/api/action-items/", {"plan": self.plan.id, "title": "Ligar para o fornecedor", "priority": "alta", "responsible": self.gestor.id, "due_date": "2020-01-01"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        item = r.json()["id"]
        r = self.client.patch(f"/api/action-items/{item}/", {"status": "bloqueado", "blocked_reason": "aguardando orçamento"}, format="json")
        self.assertEqual((r.json()["status"], r.json()["blocked_reason"]), ("bloqueado", "aguardando orçamento"))
        r = self.client.patch(f"/api/action-items/{item}/move/", {"status": "fazendo"}, format="json")
        self.assertEqual((r.json()["status"], r.json()["blocked_reason"]), ("fazendo", ""))
        self.assertIsNotNone(r.json()["started_at"])
        self.client.patch(f"/api/action-items/{item}/move/", {"status": "feito"}, format="json")
        a = self.client.get("/api/action-items/analise/").json()
        self.assertEqual((a["total"], a["abertas"], a["atrasadas"], a["por_status"]["feito"]), (1, 0, 0, 1))
        self.assertEqual(a["por_responsavel"][0]["nome"], "Kai")
        self.assertIsNotNone(a["lead_time_medio_dias"])
        self.assertEqual(len(a["semanas"]), 8)


class EvolucaoPlanosTests(APITestCase):
    def setUp(self):
        from accounts.models import Tenant, User

        self.tenant = Tenant.objects.create(name="Acme", slug="acme-evo")
        self.gestor = User.objects.create_user("e@acme.com", "x", first_name="Eva", tenant=self.tenant, role=User.Role.GESTOR)
        self.client.force_authenticate(self.gestor)
        self.plan = ActionPlan.objects.create(tenant=self.tenant, title="Plano", status=ActionPlan.Status.RASCUNHO)

    def test_subatividades_avanco_e_acompanhamento(self):
        pai = self.client.post("/api/action-items/", {"plan": self.plan.id, "title": "Implantar cobrança"}, format="json").json()
        f1 = self.client.post("/api/action-items/", {"plan": self.plan.id, "title": "Contratar", "parent": pai["id"]}, format="json").json()
        f2 = self.client.post("/api/action-items/", {"plan": self.plan.id, "title": "Treinar", "parent": pai["id"], "progress_pct": 50}, format="json").json()
        self.assertEqual(f1["parent"], pai["id"])
        # neto não pode
        self.assertEqual(self.client.post("/api/action-items/", {"plan": self.plan.id, "title": "x", "parent": f1["id"]}, format="json").status_code, 400)
        self.client.patch(f"/api/action-items/{f1['id']}/move/", {"status": "feito"}, format="json")
        pai_atual = self.client.get(f"/api/action-items/{pai['id']}/").json()
        self.assertEqual((pai_atual["children_total"], pai_atual["children_done"], pai_atual["progress"]), (2, 1, 75))   # (100 + 50) / 2
        solo = self.client.post("/api/action-items/", {"plan": self.plan.id, "title": "Solo", "progress_pct": 25}, format="json").json()
        self.assertEqual(solo["progress"], 25)
        plano = self.client.get(f"/api/action-plans/{self.plan.id}/").json()
        self.assertEqual(plano["progress_pct"], 50)          # (75 + 25) / 2 nas atividades de 1º nível
        self.assertEqual(self.client.post("/api/action-items/", {"plan": self.plan.id, "title": "y", "progress_pct": 120}, format="json").status_code, 400)
        # acompanhamento
        r = self.client.post(f"/api/action-plans/{self.plan.id}/updates/", {"text": "Fornecedor contratado", "progress_pct": 40, "next_action": "Treinar equipe dia 20"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["author_name"], "Eva")
        plano = self.client.get(f"/api/action-plans/{self.plan.id}/").json()
        self.assertEqual((plano["last_update_text"], plano["last_next_action"], plano["status"]), ("Fornecedor contratado", "Treinar equipe dia 20", "em_andamento"))
        self.assertEqual(len(self.client.get(f"/api/action-plans/{self.plan.id}/updates/").json()), 1)

    def test_guia_do_desvio(self):
        from datetime import date

        from indicators.models import Indicator, IndicatorTarget, IndicatorValue

        ind = Indicator.objects.create(tenant=self.tenant, code="RUP", name="Ruptura", unit="%", decimals=2,
                                       polarity="menor_melhor", erp_metric="ruptura_pct")
        mes = date.today().replace(day=1)
        IndicatorTarget.objects.create(indicator=ind, period=mes, target_value=5)
        v = IndicatorValue.objects.create(indicator=ind, period=mes, value=9)
        d = Deviation.objects.get(indicator_value=v)
        r = self.client.get(f"/api/deviations/{d.id}/guia/")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["origem"], "metrica")
        self.assertTrue(r.data["impacto"] and r.data["dicas"] and r.data["causas"])
        self.assertEqual(r.data["numeros"]["meses_seguidos_vermelho"], 1)
        self.assertEqual(float(r.data["numeros"]["diferenca"]), 4.0)

    def test_plano_do_desvio_ja_vem_preenchido(self):
        from datetime import date

        from indicators.models import Indicator, IndicatorTarget, IndicatorValue

        ind = Indicator.objects.create(tenant=self.tenant, code="FAT", name="Faturamento", unit="R$", decimals=2)
        mes = date.today().replace(day=1)
        IndicatorTarget.objects.create(indicator=ind, period=mes, target_value=1000)
        v = IndicatorValue.objects.create(indicator=ind, period=mes, value=600)
        d = Deviation.objects.get(indicator_value=v)
        r = self.client.post(f"/api/deviations/{d.id}/create-plan/")
        self.assertEqual(r.status_code, 201, r.content)
        p = r.json()
        self.assertTrue(p["title"].startswith("Recuperar Faturamento"))
        self.assertIn("1.000,00", p["title"])
        self.assertEqual((p["priority"], p["items_total"], p["indicator_code"]), ("alta", 3, "FAT"))
        self.assertIsNotNone(p["when_end"])
