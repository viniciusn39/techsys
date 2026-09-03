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
        self.assertEqual(resp.json()["ritmo"]["batch_max"], 500)
        self.connector.config = {"ritmo": {"pausa_ms": 3000, "load_max": 0.5, "horas_carga_inicial": "19-07"}}
        self.connector.save()
        r = self.client.get("/api/coletor/plan/", **self.headers).json()["ritmo"]
        self.assertEqual((r["pausa_ms"], r["load_max"], r["horas_carga_inicial"], r["batch_max"]), (3000, 0.5, "19-07", 500))
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
                          "progresso": {"coletando": True, "entidades": {
                              "sales_invoice": {"janela": 4, "marca": "2026-08-01",
                                                "passe": {"esperado": 2000, "lidos": 500, "importados": 500, "em_andamento": True}},
                              "branch": {"passe": {"esperado": None, "lidos": 2, "importados": 2, "em_andamento": False, "ok": True}},
                          }}},
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
        self.assertEqual((nf["pct"], nf["esperado"], nf["lidos"], nf["em_andamento"]), (25.0, 2000, 500, True))
        br = next(e for e in d["entities"] if e["entity"] == "branch")
        self.assertEqual(br["pct"], 100.0)   # sem contagem, passe concluído = 100 %
        cr = next(e for e in d["entities"] if e["entity"] == "title_receivable")
        self.assertIsNone(cr["pct"])         # nunca coletado

    def test_painel_erp_confere_indicador_com_o_espelho(self):
        from datetime import date

        from indicators.models import Indicator, IndicatorValue

        hoje = date.today().isoformat()
        self.ingest("branch", [{"CODIGO": "1", "RAZAOSOCIAL": "Matriz"}])
        self.ingest("sales_invoice", [
            {"NUMTRANSVENDA": "10", "NUMNOTA": "10", "CODFILIAL": "1", "DTSAIDA": hoje, "CONDVENDA": 1, "VLTOTAL": "1000.00"},
            {"NUMTRANSVENDA": "11", "NUMNOTA": "11", "CODFILIAL": "1", "DTSAIDA": hoje, "CONDVENDA": 1, "VLTOTAL": "500.00"},
        ])
        ind = Indicator.objects.create(tenant=self.tenant, code="FAT", name="Faturamento", unit="R$", erp_metric="faturamento")
        IndicatorValue.objects.create(indicator=ind, period=date.today().replace(day=1), value="1500", source="agent")
        colab = User.objects.create_user("c@nb.com", "x", first_name="C", tenant=self.tenant, role=User.Role.COLABORADOR)
        gestor = User.objects.create_user("g2@nb.com", "x", first_name="G", tenant=self.tenant, role=User.Role.GESTOR)

        self.client.force_authenticate(colab)
        self.assertEqual(self.client.get("/api/erp/painel/").status_code, 403)

        self.client.force_authenticate(gestor)
        r = self.client.get("/api/erp/painel/?meses=6")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(len(d["serie"]), 6)
        self.assertEqual(d["serie"][-1]["faturamento"], 1500.0)
        self.assertEqual(d["foto"]["atual"]["qtd_notas"], 2.0)
        self.assertEqual(d["por_filial"][0]["faturamento_mes"], 1500.0)
        nf = next(c for c in d["cobertura"] if c["entity"] == "sales_invoice")
        self.assertEqual((nf["total"], nf["de"]), (2, hoje))
        fat = d["indicadores"][0]
        self.assertEqual((fat["code"], fat["valor_gravado"], fat["valor_erp"], fat["situacao"]), ("FAT", 1500.0, 1500.0, "confere"))
        self.assertEqual(d["resumo_conferencia"]["confere"], 1)

        # Modo "Mês": série por dia do mês de referência escolhido.
        d = self.client.get(f"/api/erp/painel/?meses=1&ate={hoje[:7]}").json()
        self.assertEqual(len(d["serie"]), 1)
        self.assertEqual(d["foto"]["periodo"], f"{hoje[:7]}-01")
        dia = next(x for x in d["serie_dia"] if x["dia"] == hoje)
        self.assertEqual((dia["faturamento"], dia["qtd_notas"]), (1500.0, 2))

        # Carga avançou desde o cálculo: o painel acusa a divergência.
        self.ingest("sales_invoice", [{"NUMTRANSVENDA": "12", "NUMNOTA": "12", "CODFILIAL": "1", "DTSAIDA": hoje, "CONDVENDA": 1, "VLTOTAL": "100.00"}])
        fat = self.client.get("/api/erp/painel/").json()["indicadores"][0]
        self.assertEqual((fat["valor_erp"], fat["situacao"]), (1600.0, "divergente"))

    def test_indicador_do_erp_bloqueia_lancamento_manual(self):
        from indicators.models import Indicator, IndicatorValue

        erp = Indicator.objects.create(tenant=self.tenant, code="FAT", name="Faturamento", erp_metric="faturamento")
        manual = Indicator.objects.create(tenant=self.tenant, code="NPS", name="NPS")
        gestor = User.objects.create_user("g3@nb.com", "x", first_name="G", tenant=self.tenant, role=User.Role.GESTOR)
        self.client.force_authenticate(gestor)

        r = self.client.post(f"/api/indicators/{erp.id}/values/", {"period": "2026-08-01", "value": "1"}, format="json")
        self.assertEqual(r.status_code, 400)
        r = self.client.post("/api/indicator-values/bulk/", {"values": [
            {"indicator": manual.id, "period": "2026-08-01", "value": "70"},
            {"indicator": erp.id, "period": "2026-08-01", "value": "1"},
        ]}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("FAT", str(r.json()))
        self.assertFalse(IndicatorValue.objects.filter(indicator=erp).exists())

        r = self.client.post("/api/indicator-values/bulk/", {"values": [{"indicator": manual.id, "period": "2026-08-01", "value": "70"}]}, format="json")
        self.assertEqual(r.status_code, 201)

    def test_quebra_por_periodo_valores_e_metas(self):
        from datetime import date, timedelta

        from indicators.models import Indicator, IndicatorTarget, IndicatorValue

        hoje = date.today()
        ontem = hoje - timedelta(days=1)
        self.ingest("branch", [{"CODIGO": "1", "RAZAOSOCIAL": "Matriz"}])
        self.ingest("sales_invoice", [
            {"NUMTRANSVENDA": "1", "NUMNOTA": "1", "CODFILIAL": "1", "DTSAIDA": hoje.isoformat(), "CONDVENDA": 1, "VLTOTAL": "300.00"},
            {"NUMTRANSVENDA": "2", "NUMNOTA": "2", "CODFILIAL": "1", "DTSAIDA": ontem.isoformat(), "CONDVENDA": 1, "VLTOTAL": "200.00"},
        ])
        fat = Indicator.objects.create(tenant=self.tenant, code="FAT", name="Faturamento", erp_metric="faturamento", aggregation="soma")
        IndicatorTarget.objects.create(indicator=fat, period=hoje.replace(day=1), target_value=3100)
        if ontem.month != hoje.month:
            IndicatorTarget.objects.create(indicator=fat, period=ontem.replace(day=1), target_value=3100)
        nps = Indicator.objects.create(tenant=self.tenant, code="NPS", name="NPS", aggregation="media")
        for mes in (1, 2, 3):
            IndicatorTarget.objects.create(indicator=nps, period=date(2026, mes, 1), target_value=70)
            IndicatorValue.objects.create(indicator=nps, period=date(2026, mes, 1), value=60 + mes * 10)
        gestor = User.objects.create_user("g4@nb.com", "x", first_name="G", tenant=self.tenant, role=User.Role.GESTOR)
        self.client.force_authenticate(gestor)

        # ERP por dia: valor exato do dia; meta = meta do mês ÷ dias × 1.
        d = self.client.get(f"/api/indicators/{fat.id}/breakdown/?gran=dia&n=2").json()
        self.assertTrue(d["disponivel"])
        self.assertEqual([p["value"] for p in d["periodos"]], [200.0, 300.0])
        from calendar import monthrange
        self.assertAlmostEqual(d["periodos"][-1]["target"], 3100 / monthrange(hoje.year, hoje.month)[1], places=2)

        # ERP por semana e ano somam o intervalo.
        s = self.client.get(f"/api/indicators/{fat.id}/breakdown/?gran=semana&n=1").json()
        self.assertEqual(s["periodos"][0]["value"], 500.0 if ontem.weekday() <= hoje.weekday() else 300.0)
        a = self.client.get(f"/api/indicators/{fat.id}/breakdown/?gran=ano&n=1").json()
        self.assertEqual(a["periodos"][0]["value"], 500.0)

        # Manual: semestre agrega pela média; dia não está disponível.
        sm = self.client.get(f"/api/indicators/{nps.id}/breakdown/?gran=semestre&ate=2026-06-30&n=1").json()
        self.assertEqual((sm["periodos"][0]["value"], sm["periodos"][0]["target"], sm["periodos"][0]["status"]), (80.0, 70.0, "verde"))
        self.assertFalse(self.client.get(f"/api/indicators/{nps.id}/breakdown/?gran=dia").json()["disponivel"])

    def test_metas_do_erp_alimentam_indicador_e_bloqueiam_edicao(self):
        from datetime import date

        from erp.tasks import sincronizar_metas_erp
        from indicators.models import Indicator, IndicatorTarget, IndicatorValue

        mes = date.today().replace(day=1).isoformat()
        self.ingest("branch", [{"CODIGO": "10", "RAZAOSOCIAL": "CD"}, {"CODIGO": "11", "RAZAOSOCIAL": "Loja"}])
        self.ingest("salesrep", [
            {"CODUSUR": "1", "NOME": "Ana", "VLVENDAPREV": "1000", "IS_ACTIVE": 1},
            {"CODUSUR": "2", "NOME": "Bia", "VLVENDAPREV": "500", "IS_ACTIVE": 1},
            {"CODUSUR": "3", "NOME": "Ex", "VLVENDAPREV": "9999", "IS_ACTIVE": 0},
        ])
        self.ingest("target", [
            {"EXTERNAL_ID": "10-1-M-x", "CODFILIAL": "10", "CODUSUR": "1", "TIPOMETA": "M", "DATA": mes, "VLVENDAPREV": "800", "CLIPOSPREV": 30, "MARGEMPREV": "20"},
            {"EXTERNAL_ID": "11-2-M-x", "CODFILIAL": "11", "CODUSUR": "2", "TIPOMETA": "M", "DATA": mes, "VLVENDAPREV": "200", "CLIPOSPREV": 10, "MARGEMPREV": "30"},
        ])
        fat = Indicator.objects.create(tenant=self.tenant, code="FAT", name="Fat", erp_metric="faturamento", erp_target="vlvendaprev")
        fat_cd = Indicator.objects.create(tenant=self.tenant, code="FAT_CD", name="Fat CD", erp_metric="faturamento", erp_target="vlvendaprev", erp_filters={"branch": "10"})
        rca = Indicator.objects.create(tenant=self.tenant, code="FAT_RCA", name="Fat", erp_target="rca_vlvendaprev")
        margem = Indicator.objects.create(tenant=self.tenant, code="MARGEM", name="Margem", erp_target="margemprev")
        IndicatorValue.objects.create(indicator=fat, period=mes, value="900", source="agent")

        # 4 metas do mês corrente (+ a do cadastro do RCA nos meses futuros do ano, que é constante)
        self.assertGreaterEqual(sincronizar_metas_erp(tenant_id=self.tenant.id, meses=1), 4)
        meta = lambda ind: IndicatorTarget.objects.get(indicator=ind, period=mes).target_value  # noqa: E731
        self.assertEqual(meta(fat), 1000)
        self.assertEqual(meta(fat_cd), 800)
        self.assertEqual(meta(rca), 1500)      # só ativos
        self.assertEqual(meta(margem), 22)     # (20×800 + 30×200) / 1000
        v = IndicatorValue.objects.get(indicator=fat)
        self.assertEqual((v.achievement_pct, v.status), (90, "amarelo"))  # farol recalculado com a meta nova

        # Meta diária (PCMETARCA) prevalece sobre a PCMETA e dá dia/semana exatos.
        d1, d2 = date.today().replace(day=1), date.today().replace(day=2)
        self.ingest("target_daily", [
            {"EXTERNAL_ID": "10-1-d1", "CODFILIAL": "10", "CODUSUR": "1", "DATA": d1.isoformat(), "VLVENDAPREV": "70", "NUMCLIPOS": 3},
            {"EXTERNAL_ID": "10-1-d2", "CODFILIAL": "10", "CODUSUR": "1", "DATA": d2.isoformat(), "VLVENDAPREV": "50", "NUMCLIPOS": 2},
            {"EXTERNAL_ID": "11-2-d1", "CODFILIAL": "11", "CODUSUR": "2", "DATA": d1.isoformat(), "VLVENDAPREV": "30", "NUMCLIPOS": 1},
        ])
        sincronizar_metas_erp(tenant_id=self.tenant.id, meses=1)
        self.assertEqual((meta(fat), meta(fat_cd)), (150, 120))

        gestor = User.objects.create_user("g5@nb.com", "x", first_name="G", tenant=self.tenant, role=User.Role.GESTOR)
        self.client.force_authenticate(gestor)
        q = self.client.get(f"/api/indicators/{fat_cd.id}/breakdown/?gran=dia&n=2&ate={d2.isoformat()}").json()
        self.assertEqual([p["target"] for p in q["periodos"]], [70.0, 50.0])
        r = self.client.post(f"/api/indicators/{fat.id}/targets/bulk/", {"targets": [{"period": mes, "target_value": "1"}]}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.client.get("/api/erp/targets/").json()[0]["key"], "vlvendaprev")

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
