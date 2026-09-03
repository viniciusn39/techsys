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
