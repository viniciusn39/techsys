from datetime import date, timedelta

from rest_framework.test import APITestCase

from accounts.models import Tenant, User
from strategy.models import Perspective, StrategicMap, StrategicObjective, SwotItem


class ProjetosTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Acme", slug="acme-proj")
        self.gestor = User.objects.create_user("p@acme.com", "x", first_name="Pia", tenant=self.tenant, role=User.Role.GESTOR)
        self.client.force_authenticate(self.gestor)
        self.mapa = StrategicMap.objects.create(tenant=self.tenant, name="PE 2026", year_start=2026, year_end=2028)
        persp = Perspective.objects.create(map=self.mapa, name="Financeira")
        self.objetivo = StrategicObjective.objects.create(tenant=self.tenant, perspective=persp, name="Crescer a margem")
        self.swot = SwotItem.objects.create(tenant=self.tenant, map=self.mapa, quadrant="W", text="Sem BI")

    def _projeto(self, **extra):
        body = {"title": "Projeto BI", "owner": self.gestor.id, "start_date": "2026-07-01", "end_date": "2026-09-30",
                "objectives": [self.objetivo.id], "swot_items": [self.swot.id], "partners": [self.gestor.id], **extra}
        r = self.client.post("/api/projects/", body, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()

    def _ativ(self, projeto, titulo, **extra):
        r = self.client.post("/api/project-activities/", {"project": projeto, "title": titulo, **extra}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()

    def test_projeto_liga_no_planejamento_e_numera(self):
        p1, p2 = self._projeto(), self._projeto(title="Outro")
        self.assertEqual((p1["code"], p2["code"]), (1, 2))
        self.assertEqual((p1["map"], p1["objectives"], p1["swot_items"]), (self.mapa.id, [self.objetivo.id], [self.swot.id]))
        self.assertEqual(len(self.client.get(f"/api/projects/?objectives={self.objetivo.id}").json()), 2)
        r = self.client.post("/api/projects/", {"title": "x", "owner": self.gestor.id, "start_date": "2026-02-01", "end_date": "2026-01-01"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_eap_em_niveis_avanco_e_atraso(self):
        p = self._projeto()["id"]
        ontem = (date.today() - timedelta(days=1)).isoformat()
        raiz = self._ativ(p, "Infraestrutura")
        banco = self._ativ(p, "Banco", parent=raiz["id"], status="finalizado")
        etl = self._ativ(p, "ETL", parent=raiz["id"])
        self._ativ(p, "Dimensões", parent=etl["id"], progress_pct=80, end_date=ontem)
        self._ativ(p, "Fatos", parent=etl["id"], progress_pct=40)
        self.assertEqual((banco["progress_pct"], banco["status"]), (100, "finalizado"))
        linhas = self.client.get(f"/api/projects/{p}/atividades/").json()
        self.assertEqual([l["wbs"] for l in linhas], ["1", "1.1", "1.2", "1.2.1", "1.2.2"])
        self.assertEqual([l["progress"] for l in linhas], [80, 100, 60, 80, 40])   # ETL = (80+40)/2; raiz = (100+60)/2
        self.assertEqual([l["late"] for l in linhas], [False, False, False, True, False])
        self.assertEqual(linhas[3]["status"], "em_andamento")   # saiu de 0%: começou
        proj = self.client.get(f"/api/projects/{p}/").json()
        self.assertEqual((proj["activities_count"], proj["subactivities_count"], proj["progress"], proj["late_count"], proj["status"]),
                         (1, 4, 80, 1, "em_andamento"))
        # ciclo na árvore não entra
        r = self.client.patch(f"/api/project-activities/{raiz['id']}/", {"parent": etl["id"]}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_atividade_finalizada_pode_ser_reaberta(self):
        p = self._projeto()["id"]
        a = self._ativ(p, "Banco", status="finalizado")
        # o formulário sempre manda o % junto: 100 + "em andamento" tem de reabrir, não finalizar de novo
        r = self.client.patch(f"/api/project-activities/{a['id']}/", {"status": "em_andamento", "progress_pct": 100}, format="json").json()
        self.assertEqual((r["status"], r["progress_pct"], r["done_at"]), ("em_andamento", 99, None))
        r = self.client.patch(f"/api/project-activities/{a['id']}/", {"status": "em_andamento", "progress_pct": 100}, format="json").json()
        self.assertEqual(r["status"], "finalizado")   # agora sim: subiu para 100 estando aberta

    def test_fca_e_painel(self):
        p = self._projeto()["id"]
        a = self._ativ(p, "Banco", responsible=self.gestor.id, start_date="2026-07-01", end_date="2026-07-31")
        ontem = (date.today() - timedelta(days=1)).isoformat()
        r = self.client.post("/api/project-fcas/", {"activity": a["id"], "fact": "Servidor sem espaço", "cause": "Logs", "action": "Rotacionar", "due_date": ontem, "responsible": self.gestor.id}, format="json")
        self.assertEqual((r.status_code, r.json()["alert"]), (201, "atrasado"))
        self.assertEqual(len(self.client.get(f"/api/projects/{p}/fcas/").json()), 1)
        self.assertEqual(self.client.get(f"/api/projects/{p}/atividades/").json()[0]["fcas_count"], 1)
        d = self.client.get("/api/projects/dashboard/").json()
        self.assertEqual((d["projetos"], d["atividades"], d["atrasadas"], d["por_fase"]["iniciacao"]), (1, 1, 1, 1))
        self.assertEqual(d["ranking"][0]["nome"], "Pia")
        self.assertEqual(d["timeline"][0], {"mes": "2026-07", "iniciadas": 1, "finalizadas": 0})

    def test_outra_empresa_nao_enxerga_nem_escreve(self):
        p = self._projeto()["id"]
        outro = Tenant.objects.create(name="Beta", slug="beta-proj")
        intruso = User.objects.create_user("i@beta.com", "x", tenant=outro, role=User.Role.ADMIN)
        self.client.force_authenticate(intruso)
        self.assertEqual(self.client.get("/api/projects/").json(), [])
        self.assertEqual(self.client.get(f"/api/projects/{p}/").status_code, 404)
        r = self.client.post("/api/project-activities/", {"project": p, "title": "x"}, format="json")
        self.assertIn(r.status_code, (400, 403))
        r = self.client.post("/api/projects/", {"title": "x", "owner": intruso.id, "start_date": "2026-01-01", "end_date": "2026-02-01", "objectives": [self.objetivo.id]}, format="json")
        self.assertEqual(r.status_code, 400)


class VisaoGeralTests(APITestCase):
    def test_overview_junta_planejamento_projetos_e_indicadores(self):
        tenant = Tenant.objects.create(name="Acme", slug="acme-ov")
        gestor = User.objects.create_user("o@acme.com", "x", first_name="Oto", tenant=tenant, role=User.Role.GESTOR)
        self.client.force_authenticate(gestor)
        self.assertEqual(self.client.get("/api/dashboard/overview/").json()["mapa"], None)   # empresa vazia não quebra
        mapa = StrategicMap.objects.create(tenant=tenant, name="PE", year_start=2026, year_end=2028)
        persp = Perspective.objects.create(map=mapa, name="Financeira")
        StrategicObjective.objects.create(tenant=tenant, perspective=persp, name="Margem")
        SwotItem.objects.create(tenant=tenant, map=mapa, quadrant="S", text="Marca")
        r = self.client.post("/api/projects/", {"title": "Velho", "owner": gestor.id, "start_date": "2020-01-01", "end_date": "2020-02-01"}, format="json").json()
        self.client.post("/api/project-activities/", {"project": r["id"], "title": "A"}, format="json")
        d = self.client.get("/api/dashboard/overview/").json()
        self.assertEqual((d["mapa"]["name"], d["contagens"]["objetivos"], d["contagens"]["projetos"], d["swot"]["S"]), ("PE", 1, 1, 1))
        self.assertEqual((d["projetos_atrasados"][0]["title"], d["perspectivas"][0]["atingimento"], len(d["atividades_recentes"])), ("Velho", None, 1))


class NadaDeOutraEmpresaTests(APITestCase):
    """Id de outra empresa não entra nem na criação nem na alteração — e o nome dele não volta na resposta."""

    def setUp(self):
        self.a = Tenant.objects.create(name="Alfa", slug="alfa-iso")
        self.b = Tenant.objects.create(name="Beta", slug="beta-iso")
        self.ana = User.objects.create_user("ana@iso.com", "x", first_name="Ana", tenant=self.a, role=User.Role.ADMIN)
        self.bia = User.objects.create_user("bia@iso.com", "x", first_name="Bia Secreta", tenant=self.b, role=User.Role.ADMIN)
        self.client.force_authenticate(self.ana)

    def test_reuniao_fca_e_objetivo(self):
        r = self.client.post("/api/meetings/", {"title": "x", "starts_at": "2026-03-09T08:00:00-03:00", "participants": [self.bia.id]}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertNotIn("Bia Secreta", r.content.decode())
        r = self.client.post("/api/meetings/", {"title": "x", "starts_at": "2026-03-09T08:00:00-03:00", "organizer": self.bia.id}, format="json")
        self.assertEqual(r.status_code, 400)

        mapa_b = StrategicMap.objects.create(tenant=self.b, name="PE B", year_start=2026, year_end=2026)
        persp_b = Perspective.objects.create(map=mapa_b, name="Financeira B")
        mapa_a = StrategicMap.objects.create(tenant=self.a, name="PE A", year_start=2026, year_end=2026)
        persp_a = Perspective.objects.create(map=mapa_a, name="Financeira")
        obj = self.client.post("/api/objectives/", {"perspective": persp_a.id, "name": "Crescer"}, format="json").json()
        self.assertEqual(self.client.patch(f"/api/objectives/{obj['id']}/", {"perspective": persp_b.id}, format="json").status_code, 400)
        self.assertEqual(self.client.patch(f"/api/objectives/{obj['id']}/", {"owner": self.bia.id}, format="json").status_code, 400)

        from projects.models import Project, ProjectActivity

        proj_b = Project.objects.create(tenant=self.b, code=1, title="Segredo", start_date="2026-01-01", end_date="2026-02-01")
        ativ_b = ProjectActivity.objects.create(project=proj_b, title="Atividade secreta")
        p = self.client.post("/api/projects/", {"title": "Meu", "owner": self.ana.id, "start_date": "2026-01-01", "end_date": "2026-02-01"}, format="json").json()
        a = self.client.post("/api/project-activities/", {"project": p["id"], "title": "Minha"}, format="json").json()
        f = self.client.post("/api/project-fcas/", {"activity": a["id"], "fact": "x"}, format="json").json()
        r = self.client.patch(f"/api/project-fcas/{f['id']}/", {"activity": ativ_b.id}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertNotIn("secreta", r.content.decode())


class ImportarPlanilhaTests(APITestCase):
    def test_importa_a_eap_do_csv_exportado(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        tenant = Tenant.objects.create(name="Acme", slug="acme-imp")
        gil = User.objects.create_user("gil@imp.com", "x", first_name="Gil", last_name="Souza", tenant=tenant, role=User.Role.GESTOR)
        self.client.force_authenticate(gil)
        p = self.client.post("/api/projects/", {"title": "P", "owner": gil.id, "start_date": "2026-01-01", "end_date": "2026-12-31"}, format="json").json()["id"]
        csv = ('\ufeff"EAP";"Atividade";"Responsável";"Fase";"Início";"Fim";"Situação";"Avanço %"\r\n'
               '"1";"Infraestrutura";"Gil Souza";"Execução";"01/07/2026";"31/08/2026";"Em andamento";"0"\r\n'
               '"1.1";"Banco";"gil@imp.com";"Execução";"01/07/2026";"31/07/2026";"Finalizado";"40"\r\n'
               '"1.2";"ETL";"Fulano";"Planejamento";"32/13/2026";"";"";"60%"\r\n'
               '"";"";"";"";"";"";"";""\r\n'
               '"7.1";"Órfã";"";"";"";"";"";""\r\n').encode("utf-8")
        r = self.client.post(f"/api/projects/{p}/importar/", {"file": SimpleUploadedFile("eap.csv", csv)}, format="multipart")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["criadas"], 4)
        self.assertEqual(len(r.json()["avisos"]), 3)      # responsável desconhecido, data inválida, mãe não encontrada
        linhas = self.client.get(f"/api/projects/{p}/atividades/").json()
        self.assertEqual([(l["wbs"], l["title"], l["progress"], l["responsible_name"]) for l in linhas],
                         [("1", "Infraestrutura", 80, "Gil Souza"), ("1.1", "Banco", 100, "Gil Souza"), ("1.2", "ETL", 60, ""), ("2", "Órfã", 0, "")])
        self.assertEqual(linhas[2]["phase"], "planejamento")
        ruim = self.client.post(f"/api/projects/{p}/importar/", {"file": SimpleUploadedFile("x.csv", b"a;b\n1;2\n")}, format="multipart")
        self.assertEqual(ruim.status_code, 400)
