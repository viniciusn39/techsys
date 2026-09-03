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

    @action(detail=True, methods=["post"], url_path="values")
    def set_value(self, request, pk=None):
        indicator = self.get_object()
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
