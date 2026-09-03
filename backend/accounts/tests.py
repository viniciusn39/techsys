from rest_framework.test import APITestCase

from indicators.models import Indicator

from .models import OrgUnit, Tenant, User


class TenantIsolationTests(APITestCase):
    """Teste mais importante do sistema: usuário do tenant A não vê dados do B."""

    def setUp(self):
        self.tenant_a = Tenant.objects.create(name="Empresa A", slug="empresa-a")
        self.tenant_b = Tenant.objects.create(name="Empresa B", slug="empresa-b")
        self.admin_a = User.objects.create_user(
            "admin@a.com", "senha123", first_name="Admin A",
            tenant=self.tenant_a, role=User.Role.ADMIN,
        )
        self.admin_b = User.objects.create_user(
            "admin@b.com", "senha123", first_name="Admin B",
            tenant=self.tenant_b, role=User.Role.ADMIN,
        )
        self.root = User.objects.create_user(
            "root@techsys.com", "senha123", first_name="Root", role=User.Role.ROOT,
        )
        self.unit_a = OrgUnit.objects.create(tenant=self.tenant_a, name="Comercial A")
        self.unit_b = OrgUnit.objects.create(tenant=self.tenant_b, name="Comercial B")
        self.ind_a = Indicator.objects.create(
            tenant=self.tenant_a, code="REC", name="Receita A"
        )
        self.ind_b = Indicator.objects.create(
            tenant=self.tenant_b, code="REC", name="Receita B"
        )

    def test_admin_so_ve_org_units_do_proprio_tenant(self):
        self.client.force_authenticate(self.admin_a)
        resp = self.client.get("/api/org-units/")
        names = [u["name"] for u in resp.json()]
        self.assertEqual(names, ["Comercial A"])

    def test_admin_so_ve_indicadores_do_proprio_tenant(self):
        self.client.force_authenticate(self.admin_a)
        resp = self.client.get("/api/indicators/")
        names = [i["name"] for i in resp.json()]
        self.assertEqual(names, ["Receita A"])

    def test_admin_nao_acessa_objeto_de_outro_tenant(self):
        self.client.force_authenticate(self.admin_a)
        resp = self.client.get(f"/api/indicators/{self.ind_b.id}/")
        self.assertEqual(resp.status_code, 404)

    def test_criacao_injeta_tenant_do_usuario(self):
        self.client.force_authenticate(self.admin_a)
        resp = self.client.post("/api/org-units/", {"name": "Nova Área", "kind": "area"})
        self.assertEqual(resp.status_code, 201)
        unit = OrgUnit.objects.get(id=resp.json()["id"])
        self.assertEqual(unit.tenant, self.tenant_a)

    def test_fk_cruzada_entre_tenants_rejeitada(self):
        self.client.force_authenticate(self.admin_a)
        resp = self.client.post(
            "/api/indicators/",
            {"code": "X1", "name": "KPI X", "org_unit": self.unit_b.id},
        )
        self.assertEqual(resp.status_code, 400)

    def test_root_sem_header_nao_ve_dados_de_negocio(self):
        self.client.force_authenticate(self.root)
        resp = self.client.get("/api/indicators/")
        self.assertEqual(resp.json(), [])

    def test_root_com_header_assume_tenant(self):
        self.client.force_authenticate(self.root)
        resp = self.client.get(
            "/api/indicators/", HTTP_X_TENANT_ID=str(self.tenant_a.id)
        )
        names = [i["name"] for i in resp.json()]
        self.assertEqual(names, ["Receita A"])

    def test_usuario_comum_nao_assume_outro_tenant_via_header(self):
        self.client.force_authenticate(self.admin_a)
        resp = self.client.get(
            "/api/indicators/", HTTP_X_TENANT_ID=str(self.tenant_b.id)
        )
        names = [i["name"] for i in resp.json()]
        self.assertEqual(names, ["Receita A"])

    def test_apenas_root_gerencia_tenants(self):
        self.client.force_authenticate(self.admin_a)
        self.assertEqual(self.client.get("/api/tenants/").status_code, 403)
        self.client.force_authenticate(self.root)
        self.assertEqual(self.client.get("/api/tenants/").status_code, 200)

    def test_empresa_nova_nasce_com_mapa_e_perspectivas_padrao(self):
        from strategy.models import Perspective, StrategicMap

        self.client.force_authenticate(self.root)
        resp = self.client.post(
            "/api/tenants/",
            {
                "name": "Nova Empresa",
                "slug": "nova-empresa",
                "admin_email": "admin@nova.com",
                "admin_password": "senha123",
                "admin_name": "Admin Nova",
            },
        )
        self.assertEqual(resp.status_code, 201)
        tenant = Tenant.objects.get(slug="nova-empresa")

        smap = StrategicMap.objects.get(tenant=tenant, is_active=True)
        names = list(
            Perspective.objects.filter(map=smap).order_by("order").values_list("name", flat=True)
        )
        self.assertEqual(
            names,
            ["Financeira", "Clientes", "Processos Internos", "Aprendizado e Crescimento"],
        )
        self.assertTrue(OrgUnit.objects.filter(tenant=tenant, kind="empresa").exists())
        self.assertTrue(User.objects.filter(email="admin@nova.com", tenant=tenant).exists())

    def test_exclusao_de_empresa_bloqueada_use_desativar(self):
        self.client.force_authenticate(self.root)
        resp = self.client.delete(f"/api/tenants/{self.tenant_a.id}/")
        self.assertEqual(resp.status_code, 405)

        resp = self.client.post(f"/api/tenants/{self.tenant_a.id}/activate/")
        self.assertFalse(resp.json()["is_active"])

    def test_empresa_nova_nasce_com_catalogo_padrao_de_indicadores(self):
        from strategy.provisioning import DEFAULT_INDICATORS

        self.client.force_authenticate(self.root)
        self.client.post("/api/tenants/", {"name": "Com KPIs", "slug": "com-kpis"})
        tenant = Tenant.objects.get(slug="com-kpis")

        codes = set(Indicator.objects.filter(tenant=tenant).values_list("code", flat=True))
        self.assertEqual(codes, {i["code"] for i in DEFAULT_INDICATORS})

        # Nascem ligados à unidade raiz e sem meta/lançamento.
        rec = Indicator.objects.get(tenant=tenant, code="REC")
        self.assertEqual(rec.org_unit.kind, "empresa")
        self.assertEqual(rec.polarity, "maior_melhor")
        self.assertFalse(rec.values.exists())
        self.assertFalse(rec.targets.exists())

        churn = Indicator.objects.get(tenant=tenant, code="CHURN")
        self.assertEqual(churn.polarity, "menor_melhor")

    def test_load_defaults_nao_duplica_nem_sobrescreve(self):
        from strategy.provisioning import DEFAULT_INDICATORS

        # tenant_a já tem um "REC" criado no setUp, com nome próprio.
        self.client.force_authenticate(self.admin_a)
        resp = self.client.post("/api/indicators/load-defaults/")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["created"], len(DEFAULT_INDICATORS) - 1)

        self.ind_a.refresh_from_db()
        self.assertEqual(self.ind_a.name, "Receita A")  # não foi sobrescrito

        # Rodar de novo não cria nada.
        resp = self.client.post("/api/indicators/load-defaults/")
        self.assertEqual(resp.json()["created"], 0)
        self.assertEqual(
            Indicator.objects.filter(tenant=self.tenant_a).count(), len(DEFAULT_INDICATORS)
        )

    def test_colaborador_nao_carrega_catalogo_padrao(self):
        colab = User.objects.create_user(
            "colab2@a.com", "senha123", first_name="Colab",
            tenant=self.tenant_a, role=User.Role.COLABORADOR,
        )
        self.client.force_authenticate(colab)
        self.assertEqual(self.client.post("/api/indicators/load-defaults/").status_code, 403)

    def test_admin_cria_e_reordena_perspectiva(self):
        from strategy.models import Perspective, StrategicMap

        smap = StrategicMap.objects.create(
            tenant=self.tenant_a, name="Mapa A", year_start=2026, year_end=2028
        )
        Perspective.objects.create(map=smap, name="Primeira", order=0)

        self.client.force_authenticate(self.admin_a)
        # Sem informar o mapa: entra no mapa ativo da empresa, no fim da lista.
        resp = self.client.post("/api/perspectives/", {"name": "Sustentabilidade", "color": "#1baf7a"})
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["order"], 1)

        nova_id = resp.json()["id"]
        resp = self.client.patch(f"/api/perspectives/{nova_id}/move/", {"direction": "up"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual([p["name"] for p in resp.json()], ["Sustentabilidade", "Primeira"])

    def test_perspectiva_de_outro_tenant_nao_e_visivel(self):
        from strategy.models import Perspective, StrategicMap

        smap_b = StrategicMap.objects.create(
            tenant=self.tenant_b, name="Mapa B", year_start=2026, year_end=2028
        )
        Perspective.objects.create(map=smap_b, name="Só do B", order=0)

        self.client.force_authenticate(self.admin_a)
        self.assertEqual(self.client.get("/api/perspectives/").json(), [])

    def test_colaborador_nao_cria_indicador(self):
        colab = User.objects.create_user(
            "colab@a.com", "senha123", first_name="Colab",
            tenant=self.tenant_a, role=User.Role.COLABORADOR,
        )
        self.client.force_authenticate(colab)
        resp = self.client.post("/api/indicators/", {"code": "N1", "name": "Novo"})
        self.assertEqual(resp.status_code, 403)
