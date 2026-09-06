from rest_framework.test import APITestCase

from accounts.models import Tenant, User

from .models import Ticket


class ChamadosTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Acme", slug="acme-sup")
        self.other = Tenant.objects.create(name="Outra", slug="outra-sup")
        self.gestor = User.objects.create_user("g@sup.com", "x", first_name="Gi", tenant=self.tenant, role=User.Role.GESTOR)
        self.colab = User.objects.create_user("c@sup.com", "x", first_name="Co", tenant=self.tenant, role=User.Role.COLABORADOR)
        self.root = User.objects.create_user("r@sup.com", "x", first_name="Ro", role=User.Role.ROOT)

    def test_cliente_abre_root_atende_e_cliente_avalia(self):
        self.client.force_authenticate(self.gestor)
        r = self.client.post("/api/tickets/", {"title": "Painel do ERP lento", "description": "Demora 40 s para abrir", "category": "suporte", "priority": "alta"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        tid, numero = r.json()["id"], r.json()["number"]
        self.assertEqual(numero, 1)
        self.assertEqual(r.json()["status"], "aberto")
        # cliente não muda para em_atendimento nem atribui
        self.assertEqual(self.client.patch(f"/api/tickets/{tid}/", {"status": "em_atendimento"}, format="json").status_code, 403)
        self.assertEqual(self.client.patch(f"/api/tickets/{tid}/", {"assigned_to": self.root.id}, format="json").status_code, 403)
        # colaborador da mesma empresa não vê o chamado do gestor
        self.client.force_authenticate(self.colab)
        self.assertEqual(self.client.get("/api/tickets/").json(), [])
        # root vê tudo, responde (vira em atendimento, atribuído) e deixa nota interna
        self.client.force_authenticate(self.root)
        self.assertEqual(len(self.client.get("/api/tickets/").json()), 1)
        r = self.client.post(f"/api/tickets/{tid}/messages/", {"body": "Colocamos o painel em cache; confira."}, format="json")
        self.assertEqual(r.status_code, 201)
        self.client.post(f"/api/tickets/{tid}/messages/", {"body": "cliente VIP", "is_internal": True}, format="json")
        t = Ticket.objects.get(pk=tid)
        self.assertEqual((t.status, t.assigned_to_id), ("em_atendimento", self.root.id))
        self.assertIsNotNone(t.first_response_at)
        r = self.client.patch(f"/api/tickets/{tid}/", {"status": "resolvido"}, format="json")
        self.assertEqual(r.json()["status"], "resolvido")
        resumo = self.client.get("/api/tickets/resumo/").json()
        self.assertEqual(resumo["por_status"]["resolvido"], 1)
        self.assertEqual(resumo["por_empresa"], [])
        # cliente não vê a nota interna, avalia e fecha
        self.client.force_authenticate(self.gestor)
        d = self.client.get(f"/api/tickets/{tid}/").json()
        self.assertFalse(any(m["is_internal"] for m in d["messages"]))
        self.assertEqual(len(d["messages"]), 3)   # abertura, resposta, mudança de situação
        r = self.client.patch(f"/api/tickets/{tid}/", {"rating": 5, "rating_comment": "Rápido", "status": "fechado"}, format="json")
        self.assertEqual((r.json()["rating"], r.json()["status"]), (5, "fechado"))
        self.assertEqual(self.client.patch(f"/api/tickets/{tid}/", {"rating": 9}, format="json").status_code, 400)

    def test_numeracao_por_empresa_e_isolamento(self):
        outro = User.objects.create_user("o@sup.com", "x", first_name="Ou", tenant=self.other, role=User.Role.GESTOR)
        self.client.force_authenticate(self.gestor)
        self.client.post("/api/tickets/", {"title": "A", "description": "a"}, format="json")
        self.client.force_authenticate(outro)
        r = self.client.post("/api/tickets/", {"title": "B", "description": "b"}, format="json")
        self.assertEqual(r.json()["number"], 1)
        self.assertEqual([t["title"] for t in self.client.get("/api/tickets/").json()], ["B"])
