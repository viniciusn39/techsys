from datetime import date

from django.db.models import Q
from rest_framework import status as http_status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import OrgUnit
from accounts.permissions import IsGestorOrAbove, IsTenantAdmin
from accounts.tenancy import TenantScopedViewSet, get_request_tenant

from .models import DataSource, Indicator, IndicatorTarget, IndicatorValue
from .serializers import (
    DataSourceSerializer,
    IndicatorSerializer,
    IndicatorTargetSerializer,
    IndicatorValueSerializer,
)
from .services import compute_ytd, recompute_indicator
from .sources.registry import get_source

ERP_BLOQUEADO = "Este indicador é calculado do ERP pelo agente; o lançamento manual está bloqueado."
META_ERP_BLOQUEADA = "A meta deste indicador vem do ERP; a edição manual das metas está bloqueada."


def parse_period(raw):
    try:
        d = date.fromisoformat(raw)
        return d.replace(day=1)
    except (TypeError, ValueError):
        raise ValidationError({"period": "Período inválido, use YYYY-MM-DD."})


class DataSourceViewSet(TenantScopedViewSet):
    queryset = DataSource.objects.all()
    serializer_class = DataSourceSerializer
    permission_classes = [IsTenantAdmin]
    pagination_class = None

    @action(detail=True, methods=["post"])
    def test(self, request, pk=None):
        source = get_source(self.get_object())
        if source is None:
            return Response({"ok": False, "message": "Tipo de fonte ainda não suportado (em breve)."})
        ok, message = source.test()
        return Response({"ok": ok, "message": message})


class IndicatorViewSet(TenantScopedViewSet):
    queryset = Indicator.objects.select_related("org_unit", "owner", "objective")
    serializer_class = IndicatorSerializer
    permission_classes = [IsGestorOrAbove]
    filterset_fields = ["org_unit", "objective", "owner", "is_active", "frequency"]
    search_fields = ["code", "name"]
    pagination_class = None

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["tenant"] = self.get_tenant()
        return ctx

    @action(detail=False, methods=["post"], url_path="load-defaults")
    def load_defaults(self, request):
        """Carrega o catálogo padrão de KPIs na empresa, sem duplicar os existentes."""
        from strategy.provisioning import create_default_indicators

        tenant = self.get_tenant()
        if tenant is None:
            raise PermissionDenied("Nenhuma empresa selecionada.")

        # TenantOwnedModel usa related_name="+", então a unidade raiz é buscada direto.
        root_unit = OrgUnit.objects.filter(tenant=tenant, parent__isnull=True).first()
        created = create_default_indicators(tenant, org_unit=root_unit)
        return Response(
            {
                "created": len(created),
                "indicators": IndicatorSerializer(
                    created, many=True, context=self.get_serializer_context()
                ).data,
            },
            status=http_status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["get"])
    def series(self, request, pk=None):
        indicator = self.get_object()
        year = int(request.query_params.get("year", date.today().year))
        targets = {t.period: t for t in indicator.targets.filter(period__year=year)}
        values = {v.period: v for v in indicator.values.filter(period__year=year)}
        months = [date(year, m, 1) for m in range(1, 13)]
        series = []
        for p in months:
            t, v = targets.get(p), values.get(p)
            series.append({
                "period": p,
                "target": t.target_value if t else None,
                "value": v.value if v else None,
                "achievement_pct": v.achievement_pct if v else None,
                "status": v.status if v else None,
                "note": v.note if v else "",
            })
        return Response({
            "indicator": IndicatorSerializer(indicator, context=self.get_serializer_context()).data,
            "year": year,
            "series": series,
            "ytd": compute_ytd(indicator, year),
        })

    @action(detail=True, methods=["post"], url_path="targets/bulk")
    def targets_bulk(self, request, pk=None):
        indicator = self.get_object()
        if indicator.erp_target:
            raise ValidationError(META_ERP_BLOQUEADA)
        items = request.data.get("targets", [])
        for item in items:
            period = parse_period(item.get("period"))
            raw = item.get("target_value")
            if raw in (None, ""):
                IndicatorTarget.objects.filter(indicator=indicator, period=period).delete()
                continue
            IndicatorTarget.objects.update_or_create(
                indicator=indicator, period=period, defaults={"target_value": raw}
            )
        recompute_indicator(indicator)
        return Response(
            IndicatorTargetSerializer(indicator.targets.all(), many=True).data
        )

    @action(detail=True, methods=["get"], url_path="breakdown")
    def breakdown(self, request, pk=None):
        """Valores e metas por dia, semana, mês, semestre ou ano."""
        from .breakdown import GRANULARIDADES, breakdown

        indicator = self.get_object()
        gran = request.query_params.get("gran", "mes")
        if gran not in GRANULARIDADES:
            raise ValidationError({"gran": f"Use uma de: {', '.join(GRANULARIDADES)}."})
        raw = request.query_params.get("ate")
        try:
            ate = date.fromisoformat(raw) if raw else None  # dia exato, não o mês
        except ValueError:
            raise ValidationError({"ate": "Use AAAA-MM-DD."})
        try:
            n = int(request.query_params.get("n")) if request.query_params.get("n") else None
        except ValueError:
            raise ValidationError({"n": "Inteiro."})
        return Response(breakdown(indicator, gran, ate, n))

    @action(detail=True, methods=["get"])
    def contexto(self, request, pk=None):
        """Tudo sobre o indicador numa chamada: o que é e por que importa (texto do
        catálogo), de onde vem o dado (métrica, tabelas do ERP, última carga,
        cobertura), regra da meta e do farol, onde entra na estratégia e o
        resumo do histórico (média, melhor/pior mês, tendência, ano anterior)."""
        from calendar import monthrange
        from datetime import timedelta
        from decimal import Decimal
        from statistics import mean

        from erp.metrics import get_metric, primeiro_mes_completo
        from erp.models import Branch, Connector, EntitySyncState, KpiTemplate
        from erp.targets import get_target_source
        from erp.winthor import WINTHOR_QUERIES
        from plans.models import ActionPlan, Deviation
        from strategy.models import Goal

        ind = self.get_object()
        tenant = ind.tenant
        hoje = date.today()
        e_root = getattr(request.user, "role", "") == "root"

        # --- catálogo (texto de negócio; regra técnica só para root)
        tpl = None
        if ind.erp_metric:
            tpl = KpiTemplate.objects.filter(code=ind.code, is_active=True).first() \
                or KpiTemplate.objects.filter(erp_metric=ind.erp_metric, is_active=True).first()
        sobre = {
            "descricao": (ind.description or "").split("\n\nComo é calculado:")[0].strip(),
            "como_calcula": tpl.explanation if tpl else "",
            "por_que_importa": tpl.importance if tpl else "",
            "regra_tecnica": tpl.rule if (tpl and e_root) else "",
            "origem_inteligencia": tpl.get_origin_display() if tpl else "",
            "exige_sistema": tpl.requires_system if tpl else "",
        }

        # --- fonte do dado
        metric = get_metric(ind.erp_metric) if ind.erp_metric else None
        rotulos = {q["entity"]: q.get("label", q["entity"]) for q in WINTHOR_QUERIES}
        conector = Connector.objects.filter(tenant=tenant, is_active=True).first()
        estados = {s.entity: s for s in EntitySyncState.objects.filter(connector=conector)} if conector else {}
        entidades = []
        for e in (metric.entities if metric else []):
            st = estados.get(e)
            cob = primeiro_mes_completo(tenant.id, e)
            entidades.append({
                "entity": e, "label": rotulos.get(e, e),
                "ultima_carga": st.last_ingest_at if st else None,
                "linhas": st.rows_received if st else 0,
                "cobertura_desde": cob,
            })
        filtros = dict(ind.erp_filters or {})
        if filtros.get("branch"):
            codes = filtros["branch"] if isinstance(filtros["branch"], list) else [c.strip() for c in str(filtros["branch"]).split(",")]
            nomes = {b.code: (b.trade_name or b.name) for b in Branch.objects.filter(tenant=tenant, code__in=[str(c) for c in codes])}
            filtros["filiais"] = [{"code": str(c), "name": nomes.get(str(c), "")} for c in codes]
        fonte = {
            "tipo": "erp" if ind.erp_metric else "manual",
            "metrica": metric.label if metric else "",
            "descricao_metrica": metric.description if metric else "",
            "fotografia": bool(getattr(metric.compute, "fotografia", False)) if metric else False,
            "entidades": entidades,
            "filtros": filtros,
            "agente_online": bool(conector and conector.online) if ind.erp_metric else None,
        }

        # --- meta e farol
        src = get_target_source(ind.erp_target) if ind.erp_target else None
        metas_ano = ind.targets.filter(period__year=hoje.year).count()
        meta = {
            "origem": "erp" if src else ("manual" if metas_ano else "sem_meta"),
            "fonte_erp": src.label if src else "",
            "meses_com_meta": metas_ano,
            "limiar_amarelo_pct": ind.yellow_threshold_pct,
            "polaridade": ind.polarity, "agregacao": ind.aggregation,
            "frequencia": ind.frequency, "unidade": ind.unit, "decimais": ind.decimals,
            "meta_proporcional": bool(ind.erp_metric) and ind.aggregation == Indicator.Aggregation.SOMA,
        }

        # --- estratégia
        obj = ind.objective
        estrategia = {
            "objetivo": {"id": obj.id, "name": obj.name, "perspectiva": obj.perspective.name, "mapa": obj.perspective.map.name} if obj else None,
            "metas_desdobradas": [
                {"id": g.id, "name": g.name, "level": g.level, "org_unit": getattr(g.org_unit, "name", "")}
                for g in Goal.objects.filter(indicator=ind).exclude(status=Goal.Status.CANCELADO)
            ],
            "org_unit": getattr(ind.org_unit, "name", ""),
            "owner": ind.owner.get_full_name() if ind.owner else "",
            "desvios_abertos": Deviation.objects.filter(indicator=ind).exclude(status=Deviation.Status.CONCLUIDO).count(),
            "planos": ActionPlan.objects.filter(indicator=ind).exclude(status=ActionPlan.Status.CANCELADO).count(),
        }

        # --- histórico (últimos 12 meses fechados + mês corrente)
        ini12 = (hoje.replace(day=1) - timedelta(days=1)).replace(day=1)
        for _ in range(11):
            ini12 = (ini12 - timedelta(days=1)).replace(day=1)
        vals = list(ind.values.filter(period__gte=ini12).order_by("period"))
        fechados = [v for v in vals if v.period < hoje.replace(day=1) and v.value is not None]
        q = Decimal(1).scaleb(-int(ind.decimals))

        def melhor_pior(lst):
            if not lst:
                return None, None
            ordenado = sorted(lst, key=lambda v: v.value)
            pior, melhor = (ordenado[0], ordenado[-1]) if ind.polarity == Indicator.Polarity.MAIOR_MELHOR else (ordenado[-1], ordenado[0])
            return ({"period": melhor.period, "value": melhor.value}, {"period": pior.period, "value": pior.value})

        melhor, pior = melhor_pior(fechados)
        ult3 = [Decimal(v.value) for v in fechados[-3:]]
        ant3 = [Decimal(v.value) for v in fechados[-6:-3]]
        tendencia = None
        if len(ult3) == 3 and len(ant3) == 3 and mean(ant3):
            tendencia = ((mean(ult3) - mean(ant3)) / abs(mean(ant3)) * 100).quantize(Decimal("0.1"))
        mes_ref = fechados[-1].period if fechados else None
        ano_ant = None
        if mes_ref:
            alvo = mes_ref.replace(year=mes_ref.year - 1)
            va = ind.values.filter(period=alvo).first()
            if va and va.value is not None and va.value:
                ano_ant = {"period": alvo, "value": va.value,
                           "variacao_pct": ((Decimal(fechados[-1].value) - Decimal(va.value)) / abs(Decimal(va.value)) * 100).quantize(Decimal("0.1"))}
        atingidos = sum(1 for v in fechados if v.status == IndicatorValue.Status.VERDE)
        com_meta = sum(1 for v in fechados if v.status != IndicatorValue.Status.SEM_META)
        historico = {
            "meses_fechados": len(fechados),
            "media": Decimal(mean([Decimal(v.value) for v in fechados])).quantize(q) if fechados else None,
            "melhor": melhor, "pior": pior,
            "tendencia_3m_pct": tendencia,
            "ano_anterior": ano_ant,
            "meses_meta_atingida": atingidos, "meses_com_meta": com_meta,
            "ultimo_fechado": {"period": mes_ref, "value": fechados[-1].value, "status": fechados[-1].status} if fechados else None,
            "dias_medidos_mes": min(hoje.day, monthrange(hoje.year, hoje.month)[1]) if ind.erp_metric else None,
        }
        return Response({"sobre": sobre, "fonte": fonte, "meta": meta, "estrategia": estrategia, "historico": historico})

    @action(detail=True, methods=["get"], url_path="por-filial")
    def por_filial(self, request, pk=None):
        """Valor e meta do indicador em cada filial no intervalo (?de=AAAA-MM-DD&ate=AAAA-MM-DD; padrão: mês corrente)."""
        from calendar import monthrange

        from .breakdown import por_filial

        indicator = self.get_object()
        hoje = date.today()
        try:
            de = date.fromisoformat(request.query_params["de"]) if request.query_params.get("de") else hoje.replace(day=1)
            ate = date.fromisoformat(request.query_params["ate"]) if request.query_params.get("ate") else hoje.replace(day=monthrange(hoje.year, hoje.month)[1])
        except ValueError:
            raise ValidationError({"de": "Use AAAA-MM-DD."})
        if de > ate:
            raise ValidationError({"de": "Início depois do fim."})
        return Response(por_filial(indicator, de, ate))

    @action(detail=True, methods=["post"], url_path="values")
    def set_value(self, request, pk=None):
        indicator = self.get_object()
        if indicator.erp_metric:
            raise ValidationError(ERP_BLOQUEADO)
        period = parse_period(request.data.get("period"))
        raw = request.data.get("value")
        if raw in (None, ""):
            IndicatorValue.objects.filter(indicator=indicator, period=period).delete()
            return Response({"deleted": True})
        value, _ = IndicatorValue.objects.update_or_create(
            indicator=indicator,
            period=period,
            defaults={
                "value": raw,
                "note": request.data.get("note", ""),
                "entered_by": request.user,
                "source": IndicatorValue.Source.MANUAL,
            },
        )
        return Response(IndicatorValueSerializer(value).data)


class IndicatorValueBulkView(APIView):
    permission_classes = [IsGestorOrAbove]

    def post(self, request):
        tenant = get_request_tenant(request)
        if tenant is None:
            raise PermissionDenied("Nenhuma empresa selecionada.")
        results = []
        for item in request.data.get("values", []):
            indicator = Indicator.objects.filter(
                tenant=tenant, id=item.get("indicator")
            ).first()
            if indicator is None:
                continue
            if indicator.erp_metric:
                # Valor vem do agente do ERP; lançamento manual não sobrescreve.
                raise ValidationError({"indicator": f"{indicator.code}: {ERP_BLOQUEADO}"})
            period = parse_period(item.get("period"))
            raw = item.get("value")
            if raw in (None, ""):
                continue
            value, _ = IndicatorValue.objects.update_or_create(
                indicator=indicator,
                period=period,
                defaults={
                    "value": raw,
                    "note": item.get("note", ""),
                    "entered_by": request.user,
                    "source": IndicatorValue.Source.MANUAL,
                },
            )
            results.append(IndicatorValueSerializer(value).data)
        return Response(results, status=http_status.HTTP_201_CREATED)


class DashboardSummaryView(APIView):
    def get(self, request):
        from plans.models import ActionPlan, Deviation

        tenant = get_request_tenant(request)
        if tenant is None:
            return Response({"detail": "Nenhuma empresa selecionada."}, status=400)

        period = request.query_params.get("period")
        period = parse_period(period) if period else date.today().replace(day=1)
        org_unit = request.query_params.get("org_unit")

        indicators = Indicator.objects.filter(tenant=tenant, is_active=True)
        if org_unit:
            indicators = indicators.filter(org_unit=org_unit)

        year = period.year
        months = [date(year, m, 1) for m in range(1, 13)]

        farois = {"verde": 0, "amarelo": 0, "vermelho": 0, "sem_meta": 0, "sem_lancamento": 0}
        rows = []
        heatmap = []
        evolution = {p: {"verde": 0, "amarelo": 0, "vermelho": 0, "com_meta": 0} for p in months}

        for ind in indicators.select_related("org_unit").prefetch_related("values"):
            by_period = {v.period: v for v in ind.values.all() if v.period.year == year}

            # Série do ano do indicador: alimenta sparkline, heatmap e evolução.
            for p in months:
                v = by_period.get(p)
                if v is None:
                    continue
                heatmap.append({
                    "indicator": ind.code,
                    "period": p,
                    "status": v.status,
                    "achievement_pct": v.achievement_pct,
                })
                if v.achievement_pct is not None:
                    evolution[p]["com_meta"] += 1
                    evolution[p][v.status] = evolution[p].get(v.status, 0) + 1

            v = by_period.get(period)
            if v is None:
                farois["sem_lancamento"] += 1
                continue
            farois[v.status] += 1
            rows.append({
                "id": ind.id,
                "code": ind.code,
                "name": ind.name,
                "org_unit_name": ind.org_unit.name if ind.org_unit else None,
                "unit": ind.unit,
                "decimals": ind.decimals,
                "polarity": ind.polarity,
                "value": v.value,
                "target": (t.target_value if (t := ind.targets.filter(period=period).first()) else None),
                "achievement_pct": v.achievement_pct,
                "status": v.status,
                "spark": [
                    by_period[p].achievement_pct
                    for p in months
                    if p in by_period and by_period[p].achievement_pct is not None
                ],
            })

        with_target = [r for r in rows if r["achievement_pct"] is not None]
        atingidas = len([r for r in with_target if r["status"] == "verde"])
        rows_sorted = sorted(
            with_target, key=lambda r: r["achievement_pct"]
        )

        evolution_rows = [
            {
                "period": p,
                "verde": d["verde"],
                "amarelo": d["amarelo"],
                "vermelho": d["vermelho"],
                "atingimento_pct": (
                    round(d["verde"] / d["com_meta"] * 100, 1) if d["com_meta"] else None
                ),
            }
            for p, d in evolution.items()
        ]

        deviations = Deviation.objects.filter(tenant=tenant).exclude(
            status=Deviation.Status.CONCLUIDO
        )
        plans_qs = ActionPlan.objects.filter(tenant=tenant)
        if org_unit:
            deviations = deviations.filter(indicator__org_unit=org_unit)
            plans_qs = plans_qs.filter(org_unit=org_unit)

        overdue = plans_qs.filter(
            when_end__lt=date.today(),
        ).exclude(status__in=[ActionPlan.Status.CONCLUIDO, ActionPlan.Status.CANCELADO])

        plans_total = plans_qs.count()
        plans_done = plans_qs.filter(status=ActionPlan.Status.CONCLUIDO).count()

        return Response({
            "period": period,
            "year": year,
            "farois": farois,
            "total_indicadores": indicators.count(),
            "metas_atingidas_pct": round(atingidas / len(with_target) * 100, 1) if with_target else None,
            "desvios_abertos": deviations.count(),
            "planos_atrasados": overdue.count(),
            "planos_andamento": plans_qs.filter(status=ActionPlan.Status.EM_ANDAMENTO).count(),
            "planos_total": plans_total,
            "planos_concluidos": plans_done,
            "ranking": rows_sorted,
            "piores": rows_sorted[:5],
            "melhores": list(reversed(rows_sorted[-5:])),
            "evolution": evolution_rows,
            "heatmap": heatmap,
        })
