from rest_framework.test import APITestCase

from .models import ActionPlan




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
