from datetime import date
from decimal import Decimal

from rest_framework.test import APITestCase

from accounts.models import Tenant, User
from indicators.models import Indicator, IndicatorValue

from .coletor import new_token
from .metrics import compute_metric
from .models import Branch, Connector, Customer, EntitySyncState, FinancialTitle, SalesInvoice
from .tasks import calcular_indicadores_erp
from .winthor import DEFAULT_SYNC, WINTHOR_QUERIES, queries_do_plano


class ColetorIngestTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Nordeste Boi", slug="nordesteboi")
        self.other = Tenant.objects.create(name="Outra", slug="outra")
        self.connector = Connector.objects.create(
            tenant=self.tenant, name="WinThor", ingest_token=new_token()
        )
        self.headers = {"HTTP_X_COLETOR_TOKEN": self.connector.ingest_token}

    def ingest(self, entity, items):
        return self.client.post("/api/coletor/ingest/", {"entity": entity, "items": items},
                                format="json", **self.headers)

    def test_token_invalido_e_403(self):
        resp = self.client.get("/api/coletor/plan/", HTTP_X_COLETOR_TOKEN="nada")
        self.assertEqual(resp.status_code, 403)
        resp = self.client.get("/api/coletor/plan/")
        self.assertEqual(resp.status_code, 403)

    def test_plan_devolve_consultas_na_ordem_de_valor(self):
        resp = self.client.get("/api/coletor/plan/", **self.headers)
        self.assertEqual(resp.status_code, 200)
        entidades = [q["entity"] for q in resp.json()["queries"]]
        self.assertEqual(entidades[0], "branch")
        self.assertIn("sales_invoice", entidades)
        # Toda consulta do plano tem mapa de campos correspondente.
        for q in WINTHOR_QUERIES:
            self.assertIn(q["entity"], DEFAULT_SYNC)

    def test_plan_respeita_entidades_indisponiveis(self):
        self.connector.config = {"entidades_indisponiveis": ["load", "purchase"]}
        self.connector.save()
        entidades = [q["entity"] for q in queries_do_plano(self.connector)]
        self.assertNotIn("load", entidades)
        self.assertNotIn("purchase", entidades)

    def test_ingest_cadastro_resolve_fk_por_codigo_do_erp(self):
        r = self.ingest("branch", [
            {"CODIGO": "1", "RAZAOSOCIAL": "Matriz", "CGC": "123", "IS_ACTIVE": 1},
        ])
        self.assertEqual(r.json()["imported"], 1)
        r = self.ingest("salesrep", [{"CODUSUR": 10, "NOME": "João", "IS_ACTIVE": 1}])
        self.assertEqual(r.json()["imported"], 1)
        r = self.ingest("customer", [
            {"CODCLI": 500, "CLIENTE": "Mercadinho", "CODUSUR1": 10, "BLOCKED": 0,
             "DTPRIMCOMPRA": "2026-03-10", "DTULTCOMP": "2026-08-20 00:00:00"},
        ])
        self.assertEqual(r.json()["imported"], 1, r.json())
        cli = Customer.objects.get(tenant=self.tenant, external_id="500")
        self.assertEqual(cli.sales_rep.name, "João")
        self.assertEqual(cli.first_purchase_at, date(2026, 3, 10))
        self.assertEqual(cli.last_purchase_at, date(2026, 8, 20))  # hora do DATE cortada

    def test_ingest_e_idempotente_e_atualiza(self):
        self.ingest("branch", [{"CODIGO": "1", "RAZAOSOCIAL": "Matriz"}])
        self.ingest("branch", [{"CODIGO": "1", "RAZAOSOCIAL": "Matriz Renomeada"}])
        self.assertEqual(Branch.objects.filter(tenant=self.tenant).count(), 1)
        self.assertEqual(Branch.objects.get(tenant=self.tenant).name, "Matriz Renomeada")
        state = EntitySyncState.objects.get(connector=self.connector, entity="branch")
        self.assertEqual(state.total_imported, 2)

    def test_titulos_receber_e_pagar_convivem_no_mesmo_modelo(self):
        self.ingest("title_receivable", [
            {"EXTERNAL_ID": "77-1", "VALOR": "100.50", "DTVENC": "2026-08-01", "STATUS": "open"},
        ])
        self.ingest("title_payable", [
            {"RECNUM": "77-1", "VALOR": "40", "DTVENC": "2026-08-01", "STATUS": "open", "HISTORICO": "Energia"},
        ])
        self.assertEqual(FinancialTitle.objects.filter(tenant=self.tenant).count(), 2)
        self.assertEqual(FinancialTitle.objects.get(kind="payable").amount, Decimal("40"))

    def test_dados_ficam_isolados_no_tenant_do_token(self):
        self.ingest("branch", [{"CODIGO": "1", "RAZAOSOCIAL": "Matriz"}])
        self.assertEqual(Branch.objects.filter(tenant=self.other).count(), 0)
        self.assertEqual(Branch.objects.filter(tenant=self.tenant).count(), 1)

    def test_conector_so_para_admin_do_tenant(self):
        gestor = User.objects.create_user("g@nb.com", "x", first_name="G", tenant=self.tenant, role=User.Role.GESTOR)
        admin = User.objects.create_user("adm@nb.com", "x", first_name="A", tenant=self.tenant, role=User.Role.ADMIN)
        self.client.force_authenticate(gestor)
        self.assertEqual(self.client.get("/api/erp/connectors/").status_code, 403)
        self.assertEqual(self.client.get(f"/api/erp/connectors/{self.connector.id}/progress/").status_code, 403)
        self.client.force_authenticate(admin)
        self.assertEqual(self.client.get("/api/erp/connectors/").status_code, 200)

    def test_progress_devolve_serie_por_minuto_e_estado_do_agente(self):
        self.ingest("branch", [{"CODIGO": "1", "RAZAOSOCIAL": "Matriz"}, {"CODIGO": "2", "RAZAOSOCIAL": "Loja"}])
        self.client.post("/api/coletor/heartbeat/",
                         {"oracle_ok": True, "agent_version": "1.0.2",
                          "progresso": {"coletando": True, "entidades": {"sales_invoice": {"janela": 4, "marca": "2026-08-01"}}}},
                         format="json", **self.headers)
        admin = User.objects.create_user("adm2@nb.com", "x", first_name="A", tenant=self.tenant, role=User.Role.ADMIN)
        self.client.force_authenticate(admin)
        r = self.client.get(f"/api/erp/connectors/{self.connector.id}/progress/?minutos=30")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertTrue(d["coletando"])
        self.assertEqual(d["total_geral"], 2)
        self.assertEqual(sum(p.get("branch", 0) for p in d["serie"]), 2)
        nf = next(e for e in d["entities"] if e["entity"] == "sales_invoice")
        self.assertEqual((nf["janela"], nf["janela_alvo"], nf["marca"]), (4, 24, "2026-08-01"))

    def test_heartbeat_atualiza_health_e_last_seen(self):
        r = self.client.post("/api/coletor/heartbeat/", {"oracle_ok": True, "agent_version": "1.0.0"},
                             format="json", **self.headers)
        self.assertEqual(r.status_code, 200)
        self.connector.refresh_from_db()
        self.assertTrue(self.connector.health["oracle_ok"])
        self.assertIsNotNone(self.connector.last_seen_at)
        self.assertTrue(self.connector.online)


class MetricasTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="NB", slug="nb")
        self.cd = Branch.objects.create(tenant=self.tenant, external_id="1", code="1", name="CD")
        self.loja = Branch.objects.create(tenant=self.tenant, external_id="2", code="2", name="Loja")
        cli = Customer.objects.create(tenant=self.tenant, external_id="1", name="Cli")
        for i, (branch, total, cond, cancel) in enumerate([
            (self.cd, 1000, 1, None),     # venda normal
            (self.cd, 500, 1, None),      # venda normal
            (self.loja, 300, 1, None),    # venda na loja
            (self.cd, 200, 5, None),      # bonificação: não é receita
            (self.cd, 900, 10, None),     # transferência: não é receita
            (self.cd, 400, 1, date(2026, 8, 5)),  # cancelada
        ]):
            SalesInvoice.objects.create(
                tenant=self.tenant, external_id=str(i), branch=branch, customer=cli,
                issued_at=date(2026, 8, 3), total=Decimal(total), sale_type=cond, canceled_at=cancel,
            )
        FinancialTitle.objects.create(tenant=self.tenant, external_id="a", kind="receivable",
                                      amount=Decimal(100), due_date=date(2026, 6, 1), status="open")
        FinancialTitle.objects.create(tenant=self.tenant, external_id="b", kind="receivable",
                                      amount=Decimal(300), due_date=date(2026, 12, 1), status="open")

    def test_faturamento_aplica_regras_do_winthor(self):
        # 1000 + 500 + 300 — bonificação, transferência e cancelada ficam fora.
        self.assertEqual(compute_metric("faturamento", self.tenant, date(2026, 8, 1)), Decimal("1800.00"))

    def test_faturamento_por_filial(self):
        self.assertEqual(compute_metric("faturamento", self.tenant, date(2026, 8, 1), {"branch": "2"}), Decimal("300.00"))

    def test_bonificacao_pct(self):
        self.assertEqual(compute_metric("bonificacao_pct", self.tenant, date(2026, 8, 1)), Decimal("11.11"))

    def test_inadimplencia_vencido_mais_de_30_dias(self):
        # 100 vencido em junho sobre 400 em aberto (medido em agosto)
        self.assertEqual(compute_metric("inadimplencia_pct", self.tenant, date(2026, 8, 1)), Decimal("25.00"))

    def test_mes_futuro_nao_calcula(self):
        self.assertIsNone(compute_metric("faturamento", self.tenant, date(2099, 1, 1)))

    def test_task_grava_valor_do_indicador_ligado_ao_erp(self):
        ind = Indicator.objects.create(tenant=self.tenant, code="FAT", name="Faturamento", erp_metric="faturamento")
        manual = Indicator.objects.create(tenant=self.tenant, code="NPS", name="NPS")
        gravados = calcular_indicadores_erp(tenant_id=self.tenant.id, meses=12)
        self.assertGreaterEqual(gravados, 1)
        v = IndicatorValue.objects.get(indicator=ind, period=date(2026, 8, 1))
        self.assertEqual(v.value, Decimal("1800.0000"))
        self.assertEqual(v.source, "agent")
        self.assertFalse(IndicatorValue.objects.filter(indicator=manual).exists())

    def test_espelho_vazio_nao_grava_valor(self):
        """Empresa sem carga nenhuma: indicador do ERP fica sem valor, não vira zero."""
        vazio = Tenant.objects.create(name="Vazia", slug="vazia")
        ind = Indicator.objects.create(tenant=vazio, code="RECVENC", name="Vencido",
                                       erp_metric="a_receber_vencido", polarity="menor_melhor")
        calcular_indicadores_erp(tenant_id=vazio.id, meses=3)
        self.assertFalse(IndicatorValue.objects.filter(indicator=ind).exists())

        # Com um título carregado, a métrica passa a valer (0 vencido = meta cumprida).
        FinancialTitle.objects.create(tenant=vazio, external_id="t1", kind="receivable",
                                      amount=Decimal(10), due_date=date(2099, 1, 1), status="open")
        calcular_indicadores_erp(tenant_id=vazio.id, meses=1)
        v = IndicatorValue.objects.get(indicator=ind)
        self.assertEqual(v.value, Decimal("0"))

    def test_catalogo_e_preview_pela_api(self):
        admin = User.objects.create_user("a@nb.com", "x", first_name="A", tenant=self.tenant, role=User.Role.ADMIN)
        self.client.force_authenticate(admin)
        r = self.client.get("/api/erp/metrics/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("faturamento", [m["key"] for m in r.json()])
        r = self.client.get("/api/erp/metrics/preview/?metric=faturamento&period=2026-08-01")
        self.assertEqual(Decimal(r.json()["value"]), Decimal("1800.00"))
        r = self.client.post("/api/indicators/", {"code": "X", "name": "X", "erp_metric": "nao_existe"})
        self.assertEqual(r.status_code, 400)
