"""Visão geral do planejamento: o que a página inicial mostra, numa única chamada."""
from collections import Counter
from datetime import date

from django.db.models import Q
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.access import filtrar_indicadores
from accounts.tenancy import get_request_tenant

from .current import mapa_atual
from .models import Meeting, Perspective, StrategicMap, StrategicObjective, SwotItem

TETO_ATINGIMENTO = 150   # um indicador a 900 % da meta não pode esconder os outros na média


def _media(valores):
    valores = [min(float(v), TETO_ATINGIMENTO) for v in valores if v is not None]
    return round(sum(valores) / len(valores), 1) if valores else None


class OverviewView(APIView):
    def get(self, request):
        from indicators.models import Indicator, IndicatorValue
        from plans.models import ActionPlan, Deviation
        from projects.models import Andamento, Project, ProjectActivity
        from projects.services import arvores_por_projeto, resumo_projeto

        tenant = get_request_tenant(request)
        if tenant is None:
            return Response({"detail": "Nenhuma empresa selecionada."}, status=400)
        hoje = date.today()
        ano = hoje.year

        # --- indicadores: desempenho mês a mês e por perspectiva ---------------------
        indicadores = filtrar_indicadores(request.user, Indicator.objects.filter(tenant=tenant, is_active=True))
        valores = list(
            IndicatorValue.objects.filter(indicator__in=indicadores, period__year=ano, achievement_pct__isnull=False)
            .values("indicator_id", "indicator__objective_id", "indicator__objective__perspective_id", "period", "achievement_pct", "status")
        )
        por_mes = {}
        for v in valores:
            por_mes.setdefault(v["period"], []).append(v["achievement_pct"])
        performance = [{"period": p, "realizado": _media(por_mes[p])} for p in sorted(por_mes)]
        referencia = max((p for p in por_mes if p <= hoje), default=None)   # último mês medido
        do_mes = [v for v in valores if v["period"] == referencia]

        mapa = mapa_atual(request, tenant)
        perspectivas = []
        for persp in Perspective.objects.filter(map=mapa).order_by("order", "id") if mapa else []:
            pcts = [v["achievement_pct"] for v in do_mes if v["indicator__objective__perspective_id"] == persp.id]
            perspectivas.append({
                "id": persp.id, "name": persp.name, "color": persp.color,
                "objetivos": persp.objectives.count(), "indicadores": len(pcts), "atingimento": _media(pcts),
            })

        # Objetivo alcançado: tem indicador medido no mês de referência e todos estão verdes.
        por_objetivo = {}
        for v in do_mes:
            if v["indicator__objective_id"]:
                por_objetivo.setdefault(v["indicator__objective_id"], []).append(v["status"])
        objetivos_do_mapa = set(StrategicObjective.objects.filter(tenant=tenant, perspective__map=mapa).values_list("id", flat=True))
        por_objetivo = {k: v for k, v in por_objetivo.items() if k in objetivos_do_mapa}
        objetivos_total = len(objetivos_do_mapa)
        objetivos_ok = sum(1 for s in por_objetivo.values() if all(x == "verde" for x in s))

        # --- projetos ------------------------------------------------------------------
        projetos_qs = Project.objects.filter(tenant=tenant)
        if mapa is not None and StrategicMap.objects.filter(tenant=tenant).count() > 1:
            # Vários planejamentos: a tela inteira é do que está em uso (e dos projetos antigos, sem planejamento).
            projetos_qs = projetos_qs.filter(Q(map=mapa) | Q(map__isnull=True))
        projetos = list(projetos_qs.select_related("owner"))
        resumos = {pid: resumo_projeto(l) for pid, l in arvores_por_projeto(projetos, hoje).items()}
        abertos = [p for p in projetos if p.status not in (Andamento.FINALIZADO, Andamento.CANCELADO)]
        atrasados = sorted(
            ({"id": p.id, "code": p.code, "title": p.title, "status": p.status, "progress": resumos[p.id]["progress"],
              "dias": (hoje - p.end_date).days}
             for p in abertos if p.end_date < hoje and resumos[p.id]["progress"] < 100),
            key=lambda d: -d["dias"],
        )
        recentes = [
            {"id": a.id, "project": a.project_id, "project_title": a.project.title, "title": a.title,
             "status": a.status, "created_at": a.created_at}
            for a in ProjectActivity.objects.filter(project__in=projetos).select_related("project").order_by("-created_at")[:6]
        ]
        criadas = Counter(
            timezone.localtime(a).strftime("%Y-%m") for a in ProjectActivity.objects.filter(project__in=projetos, created_at__year=ano)
            .values_list("created_at", flat=True)
        )

        # --- SWOT e agenda ---------------------------------------------------------------
        swot = Counter(SwotItem.objects.filter(tenant=tenant, map=mapa).values_list("quadrant", flat=True)) if mapa else {}
        agenda = [
            {"id": m.id, "title": m.title, "kind_label": m.get_kind_display(), "starts_at": m.starts_at, "location": m.location}
            for m in Meeting.objects.filter(tenant=tenant, status=Meeting.Status.AGENDADA, starts_at__gte=timezone.now()).order_by("starts_at")[:5]
        ]

        return Response({
            "mapa": {"id": mapa.id, "name": mapa.name} if mapa else None,
            "referencia": referencia,
            "contagens": {
                "planejamentos": StrategicMap.objects.filter(tenant=tenant).count(),
                "objetivos": objetivos_total, "objetivos_alcancados": objetivos_ok, "objetivos_medidos": len(por_objetivo),
                "indicadores": indicadores.count(),
                "projetos": len(projetos), "projetos_abertos": len(abertos),
                "planos_abertos": ActionPlan.objects.filter(tenant=tenant, status__in=[ActionPlan.Status.RASCUNHO, ActionPlan.Status.EM_ANDAMENTO]).count(),
                "desvios_abertos": Deviation.objects.filter(tenant=tenant).exclude(status=Deviation.Status.CONCLUIDO).count(),
            },
            "performance": performance,
            "performance_media": _media([p["realizado"] for p in performance]),
            "perspectivas": perspectivas,
            "projetos_por_status": dict(Counter(p.status for p in projetos)),
            "projetos_atrasados": atrasados[:6],
            "projetos_progresso_medio": round(sum(r["progress"] for r in resumos.values()) / len(resumos)) if resumos else 0,
            "atividades_por_mes": [{"mes": m, "criadas": n} for m, n in sorted(criadas.items())],
            "atividades_recentes": recentes,
            "swot": {q: swot.get(q, 0) for q in ("S", "W", "O", "T")},
            "agenda": agenda,
        })
