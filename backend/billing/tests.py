from datetime import date, timedelta

from rest_framework.test import APITestCase

from accounts.models import Tenant, User


class FaturasTests(APITestCase):
    def test_root_lanca_empresa_so_consulta_as_dela(self):
        a = Tenant.objects.create(name="Alfa", slug="alfa-fat")
        b = Tenant.objects.create(name="Beta", slug="beta-fat")
        root = User.objects.create_user("root@fat.com", "x", role=User.Role.ROOT)
        admin = User.objects.create_user("adm@fat.com", "x", tenant=a, role=User.Role.ADMIN)
        gestor = User.objects.create_user("ges@fat.com", "x", tenant=a, role=User.Role.GESTOR)
        ontem = (date.today() - timedelta(days=1)).isoformat()
        self.client.force_authenticate(root)
        for tenant, numero, venc, status in [(a, "2026-001", ontem, "aberta"), (a, "2026-002", "2030-01-10", "paga"), (b, "2026-001", ontem, "aberta")]:
            r = self.client.post("/api/faturas/", {"tenant": tenant.id, "number": numero, "description": "Mensalidade", "reference": "2026-09-01", "amount": "500.00", "due_date": venc, "status": status}, format="json")
            self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(len(self.client.get("/api/faturas/").json()), 3)
        self.client.force_authenticate(admin)
        lista = self.client.get("/api/faturas/").json()
        self.assertEqual(sorted((f["number"], f["overdue"]) for f in lista), [("2026-001", True), ("2026-002", False)])
        self.assertIsNotNone([f for f in lista if f["status"] == "paga"][0]["paid_at"])
        resumo = self.client.get("/api/faturas/resumo/").json()
        self.assertEqual((float(resumo["total"]), resumo["pagas"], resumo["abertas"], resumo["atrasadas"]), (1000.0, 1, 0, 1))
        self.assertEqual(self.client.post("/api/faturas/", {"number": "x", "description": "x", "reference": "2026-09-01", "amount": "1", "due_date": ontem}, format="json").status_code, 403)
        self.assertEqual(self.client.patch(f"/api/faturas/{lista[0]['id']}/", {"status": "paga"}, format="json").status_code, 403)
        self.client.force_authenticate(gestor)
        self.assertEqual(self.client.get("/api/faturas/").json(), [])
