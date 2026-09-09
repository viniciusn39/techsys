from rest_framework.test import APITestCase

from accounts.models import Tenant, User
from indicators.models import Indicator

from .models import Perspective, StrategicMap, StrategicObjective


class MapaEstrategicoTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Acme", slug="acme")
        self.other = Tenant.objects.create(name="Outra", slug="outra")
        self.admin = User.objects.create_user(
            "admin@acme.com", "senha123", first_name="Admin",
            tenant=self.tenant, role=User.Role.ADMIN,
        )

        self.map = StrategicMap.objects.create(
            tenant=self.tenant, name="Mapa 2026", year_start=2026, year_end=2028
        )
        self.financeira = Perspective.objects.create(map=self.map, name="Financeira", order=0)
        self.processos = Perspective.objects.create(map=self.map, name="Processos", order=1)

        self.receita = StrategicObjective.objects.create(
            tenant=self.tenant, perspective=self.financeira, name="Crescer receita"
        )
        self.entregas = StrategicObjective.objects.create(
            tenant=self.tenant, perspective=self.processos, name="Melhorar entregas"
        )
        self.client.force_authenticate(self.admin)

    # --- arrastar e soltar --------------------------------------------------

    def test_layout_salva_posicao(self):
        resp = self.client.post(
            "/api/objectives/layout/",
            {"positions": [{"id": self.entregas.id, "pos_x": 40.5, "pos_y": 12.0}]},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.entregas.refresh_from_db()
        self.assertAlmostEqual(self.entregas.pos_x, 40.5)
        self.assertAlmostEqual(self.entregas.pos_y, 12.0)

    def test_soltar_em_outra_faixa_troca_a_perspectiva(self):
        self.client.post(
            "/api/objectives/layout/",
            {"positions": [{
                "id": self.entregas.id, "pos_x": 10, "pos_y": 20,
                "perspective": self.financeira.id,
            }]},
            format="json",
        )
        self.entregas.refresh_from_db()
        self.assertEqual(self.entregas.perspective, self.financeira)

    def test_layout_ignora_objetivo_de_outro_tenant(self):
        alheio = StrategicObjective.objects.create(
            tenant=self.other,
            perspective=Perspective.objects.create(
                map=StrategicMap.objects.create(
                    tenant=self.other, name="M", year_start=2026, year_end=2027
                ),
                name="P",
            ),
            name="Alheio",
        )
        resp = self.client.post(
            "/api/objectives/layout/",
            {"positions": [{"id": alheio.id, "pos_x": 99, "pos_y": 99}]},
            format="json",
        )
        self.assertEqual(resp.json(), [])
        alheio.refresh_from_db()
        self.assertIsNone(alheio.pos_x)

    # --- setas de causa e efeito -------------------------------------------

    def test_toggle_link_liga_e_desliga(self):
        url = f"/api/objectives/{self.entregas.id}/toggle-link/"

        resp = self.client.post(url, {"target": self.receita.id})
        self.assertTrue(resp.json()["linked"])
        self.assertIn(self.receita, self.entregas.contributes_to.all())

        resp = self.client.post(url, {"target": self.receita.id})
        self.assertFalse(resp.json()["linked"])
        self.assertNotIn(self.receita, self.entregas.contributes_to.all())

    def test_objetivo_nao_liga_em_si_mesmo(self):
        resp = self.client.post(
            f"/api/objectives/{self.receita.id}/toggle-link/",
            {"target": self.receita.id},
        )
        self.assertEqual(resp.status_code, 400)

    # --- aplicar sugestão da IA --------------------------------------------

    def test_apply_suggestion_cria_objetivos_e_ligacoes(self):
        Indicator.objects.create(tenant=self.tenant, code="REC", name="Receita")

        resp = self.client.post(
            f"/api/strategic-maps/{self.map.id}/apply-suggestion/",
            {
                "objectives": [
                    {"perspective": "Financeira", "name": "Ampliar margem",
                     "description": "Elevar a margem bruta", "indicator_code": "REC"},
                    {"perspective": "Processos", "name": "Reduzir refugo",
                     "description": "Cortar perdas na linha", "indicator_code": None},
                    # Perspectiva inexistente: deve ser descartada.
                    {"perspective": "Inexistente", "name": "Ignorar",
                     "description": "", "indicator_code": None},
                ],
                "links": [{"from": "Reduzir refugo", "to": "Ampliar margem"}],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["created"], 2)
        self.assertEqual(resp.json()["linked"], 1)

        refugo = StrategicObjective.objects.get(tenant=self.tenant, name="Reduzir refugo")
        margem = StrategicObjective.objects.get(tenant=self.tenant, name="Ampliar margem")
        self.assertIn(margem, refugo.contributes_to.all())
        self.assertFalse(StrategicObjective.objects.filter(name="Ignorar").exists())

        # O indicador sugerido foi amarrado ao objetivo criado.
        self.assertEqual(Indicator.objects.get(code="REC").objective, margem)

    def test_apply_suggestion_nao_duplica_objetivo_existente(self):
        resp = self.client.post(
            f"/api/strategic-maps/{self.map.id}/apply-suggestion/",
            {
                "objectives": [
                    {"perspective": "Financeira", "name": "Crescer receita",
                     "description": "já existe", "indicator_code": None}
                ],
                "links": [],
            },
            format="json",
        )
        self.assertEqual(resp.json()["created"], 0)
        self.assertEqual(
            StrategicObjective.objects.filter(tenant=self.tenant, name="Crescer receita").count(), 1
        )


class DiagnosticoEIdentidadeTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Acme", slug="acme2")
        self.other = Tenant.objects.create(name="Outra", slug="outra2")
        self.gestor = User.objects.create_user("g@acme.com", "x", first_name="G", tenant=self.tenant, role=User.Role.GESTOR)
        self.map = StrategicMap.objects.create(tenant=self.tenant, name="Mapa", year_start=2026, year_end=2028)
        persp = Perspective.objects.create(map=self.map, name="Financeira")
        self.obj = StrategicObjective.objects.create(tenant=self.tenant, perspective=persp, name="Crescer")
        self.client.force_authenticate(self.gestor)

    def test_swot_e_canvas_ficam_no_mapa_ativo(self):
        r = self.client.post("/api/swot/", {"quadrant": "S", "text": "Frota própria", "impact": 5, "objective": self.obj.id}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["objective_name"], "Crescer")
        self.assertEqual(self.client.post("/api/swot/", {"quadrant": "S", "text": "x", "impact": 9}, format="json").status_code, 400)
        r = self.client.post("/api/canvas/", {"block": "proposta", "text": "Carne fresca em 24 h"}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(len(self.client.get("/api/swot/").json()), 1)
        self.assertEqual(self.client.get("/api/canvas/").json()[0]["block_label"], "Proposta de valor")
        # outro tenant não enxerga
        outro = User.objects.create_user("o@outra.com", "x", first_name="O", tenant=self.other, role=User.Role.GESTOR)
        self.client.force_authenticate(outro)
        self.assertEqual(self.client.get("/api/swot/").json(), [])

    def test_stakeholder_estrategia_e_reuniao(self):
        r = self.client.post("/api/stakeholders/", {"name": "Sócio", "kind": "interno", "influence": 5, "interest": 5}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["strategy"], "gerenciar de perto")
        sid = r.json()["id"]
        r = self.client.post("/api/meetings/", {
            "title": "Reunião de resultados", "kind": "resultados", "starts_at": "2026-09-10T09:00:00Z",
            "participants": [self.gestor.id], "stakeholders": [sid], "agenda": "Faturamento",
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["organizer_name"], "G")
        self.assertEqual(r.json()["stakeholder_names"], ["Sócio"])
        self.assertEqual(len(self.client.get("/api/meetings/?de=2026-09-01&ate=2026-09-30").json()), 1)
        self.assertEqual(len(self.client.get("/api/meetings/?de=2026-10-01").json()), 0)

    def test_proposito_no_mapa(self):
        admin = User.objects.create_user("a@acme.com", "x", first_name="A", tenant=self.tenant, role=User.Role.ADMIN)
        self.client.force_authenticate(admin)
        r = self.client.patch(f"/api/strategic-maps/{self.map.id}/", {"purpose": "Alimentar bem"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(self.client.get("/api/strategic-maps/active/").json()["purpose"], "Alimentar bem")


class GoalResumoTests(TestCase):
    def test_resumo_do_indicador_ligado(self):
        from datetime import date

        from accounts.models import Tenant
        from indicators.models import Indicator, IndicatorTarget, IndicatorValue
        from strategy.models import Goal
        from strategy.serializers import GoalSerializer

        t = Tenant.objects.create(name="G", slug="g-resumo")
        ind = Indicator.objects.create(tenant=t, code="FAT", name="Fat", unit="R$", decimals=2, aggregation="soma")
        ano = date.today().year
        for m in range(1, 13):
            IndicatorTarget.objects.create(indicator=ind, period=date(ano, m, 1), target_value=100)
        IndicatorValue.objects.create(indicator=ind, period=date(ano, 1, 1), value=90)
        g = Goal.objects.create(tenant=t, name="Meta", indicator=ind)
        r = GoalSerializer(g).data["indicator_resumo"]
        self.assertEqual((float(r["meta_ano"]), float(r["realizado_ano"])), (1200.0, 90.0))
