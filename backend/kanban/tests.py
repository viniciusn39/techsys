from datetime import date, timedelta

from rest_framework.test import APITestCase

from accounts.models import Tenant, User


class KanbanTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Acme", slug="acme-kb")
        self.gestor = User.objects.create_user("g@kb.com", "x", first_name="Gil", tenant=self.tenant, role=User.Role.GESTOR)
        self.colab = User.objects.create_user("c@kb.com", "x", first_name="Caio", tenant=self.tenant, role=User.Role.COLABORADOR)
        self.client.force_authenticate(self.gestor)
        self.board = self.client.post("/api/kanban-boards/", {"name": "Sprint 1"}, format="json").json()["id"]

    def _tarefa(self, **extra):
        r = self.client.post("/api/kanban-tasks/", {"board": self.board, "title": "Configurar banco", **extra}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()

    def test_quadro_checklist_historico_e_analise(self):
        ontem = (date.today() - timedelta(days=1)).isoformat()
        t = self._tarefa(responsible=self.colab.id, due_date=ontem, priority="alta",
                         checklist=[{"text": "Criar usuário", "done": True}, {"text": "  "}, {"text": "Backup"}])
        self.assertEqual((t["late"], t["days_late"], len(t["checklist"]), t["checklist_done"]), (True, 1, 2, 1))
        r = self.client.patch(f"/api/kanban-tasks/{t['id']}/move/", {"status": "concluido"}, format="json").json()
        self.assertEqual((r["status"], r["late"]), ("concluido", False))
        self.assertIsNotNone(r["done_at"])
        hist = [h["text"] for h in self.client.get(f"/api/kanban-tasks/{t['id']}/historico/").json()]
        self.assertEqual(hist, ["Moveu de “A fazer” para “Concluído”.", "Criou a tarefa."])
        self._tarefa(title="Outra", due_date=ontem)
        a = self.client.get("/api/kanban-tasks/analise/").json()
        self.assertEqual((a["total"], a["por_status"]["concluido"], a["atrasadas"], a["conclusao_pct"]), (2, 1, 1, 50))
        self.assertEqual(a["por_responsavel"][0]["nome"], "Caio")

    def test_comunicacao_pendente_aguardando_concluida(self):
        t = self._tarefa()
        m = self.client.post(f"/api/kanban-tasks/{t['id']}/mensagens/", {"recipient": self.colab.id, "text": "Qual a senha?"}, format="json")
        self.assertEqual((m.status_code, m.json()["status"]), (201, "pendente"))
        mid = m.json()["id"]
        self.client.force_authenticate(self.colab)
        self.assertEqual(self.client.get("/api/kanban-mensagens/resumo/").json()["comigo"], 1)
        r = self.client.post(f"/api/kanban-mensagens/{mid}/responder/", {"text": "Está no cofre."}, format="json").json()
        self.assertEqual((r["status"], len(r["replies"])), ("aguardando", 1))
        self.assertEqual(self.client.post(f"/api/kanban-mensagens/{mid}/confirmar/").status_code, 403)   # só quem pediu confirma
        self.client.force_authenticate(self.gestor)
        self.assertEqual(self.client.get("/api/kanban-mensagens/resumo/").json()["comigo"], 1)
        self.assertEqual(self.client.post(f"/api/kanban-mensagens/{mid}/confirmar/").json()["status"], "concluida")
        self.assertEqual(self.client.get("/api/kanban-mensagens/?status=concluida").json()[0]["task_title"], "Configurar banco")

    def test_colaborador_move_tarefa_mas_nao_cria_board_e_outra_empresa_nao_ve(self):
        t = self._tarefa()
        self.client.force_authenticate(self.colab)
        self.assertEqual(self.client.patch(f"/api/kanban-tasks/{t['id']}/move/", {"status": "em_progresso"}, format="json").status_code, 200)
        self.assertEqual(self.client.post("/api/kanban-boards/", {"name": "x"}, format="json").status_code, 403)
        outro = Tenant.objects.create(name="Beta", slug="beta-kb")
        intruso = User.objects.create_user("i@kb.com", "x", tenant=outro, role=User.Role.ADMIN)
        self.client.force_authenticate(intruso)
        self.assertEqual(self.client.get("/api/kanban-tasks/").json(), [])
        self.assertEqual(self.client.post("/api/kanban-tasks/", {"board": self.board, "title": "x"}, format="json").status_code, 400)
