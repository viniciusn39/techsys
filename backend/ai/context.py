"""Monta o contexto (JSON-serializável) que a IA recebe sobre a empresa.

O assistente precisa enxergar o sistema inteiro: identidade e mapa
estratégico, indicadores com série recente, metas desdobradas, desvios com o
guia de tratamento, planos com atividades e acompanhamento, SWOT, Canvas,
stakeholders, agenda e chamados. Tudo compacto, em pt-BR e respeitando o
perfil de acesso de quem pergunta.
"""
from datetime import date, timedelta


def _d(v):
    return v.isoformat() if v else None


def _num(v, dec=2):
    if v is None:
        return None
    try:
        return round(float(v), dec)
    except (TypeError, ValueError):
        return v


def indicator_series(indicator, year=None):
    year = year or date.today().year
    targets = {t.period: t.target_value for t in indicator.targets.filter(period__year=year)}
    rows = []
    for v in indicator.values.filter(period__year=year).order_by("period"):
        rows.append({
            "periodo": v.period.strftime("%Y-%m"),
            "meta": targets.get(v.period),
            "realizado": v.value,
            "atingimento_pct": v.achievement_pct,
            "farol": v.status,
        })
    return rows


def _indicadores(tenant, user, meses=6):
    from indicators.models import Indicator, IndicatorTarget, IndicatorValue
    from indicators.services import meta_proporcional

    qs = Indicator.objects.filter(tenant=tenant, is_active=True).select_related("org_unit", "objective", "owner")
    if user is not None:
        from accounts.access import filtrar_indicadores

        qs = filtrar_indicadores(user, qs)
    inds = list(qs.order_by("code"))
    ids = [i.id for i in inds]
    desde = (date.today().replace(day=1) - timedelta(days=31 * (meses - 1))).replace(day=1)
    valores = {}
    for v in IndicatorValue.objects.filter(indicator_id__in=ids, period__gte=desde).order_by("period"):
        valores.setdefault(v.indicator_id, []).append(v)
    metas = {}
    for t in IndicatorTarget.objects.filter(indicator_id__in=ids, period__gte=desde):
        metas[(t.indicator_id, t.period)] = t.target_value

    out = []
    for ind in inds:
        serie = []
        for v in valores.get(ind.id, []):
            meta = metas.get((ind.id, v.period))
            meta_usada = meta_proporcional(ind, v.period, meta, v.source) if meta is not None else None
            serie.append({
                "mes": v.period.strftime("%Y-%m"), "realizado": _num(v.value, ind.decimals),
                "meta": _num(meta_usada, ind.decimals), "atingimento_pct": _num(v.achievement_pct, 1), "farol": v.status,
            })
        ultimo = serie[-1] if serie else None
        out.append({
            "codigo": ind.code, "nome": ind.name, "setor": ind.sector or None,
            "area": ind.org_unit.name if ind.org_unit else None,
            "responsavel": ind.owner.first_name if ind.owner else None,
            "unidade": ind.unit, "polaridade": ind.polarity, "agregacao": ind.aggregation,
            "fonte": "ERP (agente)" if ind.erp_metric else "manual",
            "objetivo_estrategico": ind.objective.name if ind.objective else None,
            "ultimo_mes": ultimo["mes"] if ultimo else None,
            "ultimo_realizado": ultimo["realizado"] if ultimo else None,
            "ultimo_atingimento_pct": ultimo["atingimento_pct"] if ultimo else None,
            "farol": ultimo["farol"] if ultimo else None,
            "serie_recente": serie,
        })
    return out, {i.id for i in inds}


def _mapa(tenant):
    from strategy.models import Goal, StrategicMap

    mapa = StrategicMap.objects.filter(tenant=tenant, is_active=True).first()
    if not mapa:
        return None, {}
    perspectivas = []
    for p in mapa.perspectives.order_by("order").prefetch_related("objectives__indicators", "objectives__owner", "objectives__contributes_to"):
        perspectivas.append({
            "nome": p.name,
            "objetivos": [{
                "nome": o.name, "descricao": o.description or None,
                "responsavel": o.owner.first_name if o.owner else None,
                "indicadores": [i.code for i in o.indicators.all() if i.is_active],
                "contribui_para": [c.name for c in o.contributes_to.all()],
            } for o in p.objectives.order_by("order")],
        })
    metas = [{
        "nome": g.name, "nivel": g.level, "area": g.org_unit.name if g.org_unit else None,
        "responsavel": g.owner.first_name if g.owner else None,
        "indicador": g.indicator.code if g.indicator else None,
        "objetivo": g.objective.name if g.objective else None,
        "meta_pai": g.parent.name if g.parent else None, "status": g.status,
    } for g in Goal.objects.filter(tenant=tenant).select_related("org_unit", "owner", "indicator", "objective", "parent")[:80]]
    identidade = {
        "nome_do_mapa": mapa.name, "horizonte": f"{mapa.year_start}-{mapa.year_end}",
        "proposito": mapa.purpose or None, "missao": mapa.mission or None,
        "visao": mapa.vision or None, "valores": mapa.values_text or None,
    }
    return {"identidade": identidade, "perspectivas": perspectivas, "metas_desdobradas": metas}, {"mapa": mapa}


def _diagnostico(tenant, mapa):
    from strategy.models import CanvasItem, Stakeholder, SwotItem, SwotStrategy

    if not mapa:
        return None
    swot = {}
    for s in SwotItem.objects.filter(map=mapa).select_related("objective").order_by("quadrant", "order"):
        swot.setdefault(s.get_quadrant_display(), []).append({
            "item": s.text, "impacto_1a5": s.impact, "objetivo": s.objective.name if s.objective else None,
        })
    estrategias = [{"tipo": e.get_kind_display(), "estrategia": e.text, "objetivo": e.objective.name if e.objective else None}
                   for e in SwotStrategy.objects.filter(map=mapa).select_related("objective")]
    canvas = {}
    for c in CanvasItem.objects.filter(map=mapa).order_by("block", "order"):
        canvas.setdefault(c.get_block_display(), []).append(c.text)
    stakeholders = [{
        "nome": s.name, "tipo": s.get_kind_display(), "organizacao": s.organization or None, "papel": s.role or None,
        "influencia_1a5": s.influence, "interesse_1a5": s.interest, "expectativas": s.expectations or None,
    } for s in Stakeholder.objects.filter(tenant=tenant, is_active=True)[:40]]
    return {"swot": swot, "estrategias_swot": estrategias, "canvas": canvas, "stakeholders": stakeholders}


def _desvios(tenant, ids_permitidos):
    from erp.guia_desvios import guia_desvio
    from plans.models import Deviation

    out = []
    com_guia = set()
    qs = Deviation.objects.filter(tenant=tenant, indicator_id__in=ids_permitidos).exclude(status="concluido") \
        .select_related("indicator", "indicator_value").order_by("-indicator_value__period", "indicator__code")
    for d in qs[:40]:
        item = {
            "indicador": d.indicator.code, "nome": d.indicator.name,
            "mes": d.indicator_value.period.strftime("%Y-%m"), "status": d.status,
            "realizado": _num(d.indicator_value.value, d.indicator.decimals),
            "atingimento_pct": _num(d.indicator_value.achievement_pct, 1),
            "causa_raiz": d.root_cause or None,
            "planos": [p.title for p in d.action_plans.all()],
        }
        try:
            g = guia_desvio(d)
            item["faltou_para_a_meta"] = g["numeros"]["diferenca"]
            item["meses_seguidos_vermelho"] = g["numeros"]["meses_seguidos_vermelho"]
            if d.indicator_id not in com_guia:  # texto do guia uma vez por indicador (o mais recente)
                com_guia.add(d.indicator_id)
                item["guia"] = {"impacto": g["impacto"], "causas_comuns": g["causas"], "por_onde_comecar": g["dicas"]}
        except Exception:  # guia é apoio; nunca derruba o contexto
            pass
        out.append(item)
    return out


def _planos(tenant):
    from plans.models import ActionPlan
    from plans.serializers import ActionPlanSerializer

    out = []
    qs = ActionPlan.objects.filter(tenant=tenant).exclude(status="cancelado") \
        .select_related("who", "indicator", "objective", "org_unit").prefetch_related("items__responsible", "updates__author")
    for p in qs.order_by("-created_at")[:40]:
        itens = list(p.items.all())
        por_pai = {}
        for i in itens:
            por_pai.setdefault(i.parent_id, []).append(i)

        def item(i):
            d = {"atividade": i.title, "status": i.status, "responsavel": i.responsible.first_name if i.responsible else None,
                 "prazo": _d(i.due_date), "avanco_pct": i.progress, "prioridade": i.priority}
            if i.status == "bloqueado" and i.blocked_reason:
                d["motivo_bloqueio"] = i.blocked_reason
            subs = por_pai.get(i.id, [])
            if subs:
                d["subatividades"] = [item(s) for s in subs]
            return d

        ultimas = list(p.updates.all()[:3])
        out.append({
            "titulo": p.title, "status": p.status, "etapa_pdca": p.pdca_stage, "prioridade": p.priority,
            "origem": p.origin, "indicador": p.indicator.code if p.indicator else None,
            "objetivo": p.objective.name if p.objective else None,
            "responsavel": p.who.first_name if p.who else None,
            "inicio": _d(p.when_start), "prazo": _d(p.when_end),
            "o_que": p.what or None, "por_que": p.why or None, "onde": p.where or None,
            "como": p.how or None, "quanto": _num(p.how_much) if p.how_much is not None else None,
            "avanco_pct": ActionPlanSerializer().get_progress_pct(p),
            "atividades": [item(i) for i in por_pai.get(None, [])],
            "acompanhamento_recente": [{
                "data": _d(u.created_at.date()), "autor": u.author.first_name if u.author else None,
                "texto": u.text, "avanco_informado_pct": u.progress_pct, "proxima_acao": u.next_action or None,
            } for u in ultimas],
        })
    return out


def _agenda(tenant):
    from strategy.models import Meeting

    hoje = date.today()
    qs = Meeting.objects.filter(tenant=tenant, starts_at__date__gte=hoje - timedelta(days=60),
                                starts_at__date__lte=hoje + timedelta(days=60)).select_related("org_unit", "organizer")
    return [{
        "titulo": m.title, "tipo": m.get_kind_display(), "status": m.status, "quando": m.starts_at.strftime("%Y-%m-%d %H:%M"),
        "area": m.org_unit.name if m.org_unit else None, "organizador": m.organizer.first_name if m.organizer else None,
        "pauta": m.agenda or None, "decisoes": m.decisions or None,
    } for m in qs.order_by("starts_at")[:30]]


def _chamados(tenant):
    from support.models import Ticket

    return [{
        "numero": t.number, "titulo": t.title, "categoria": t.get_category_display(), "prioridade": t.priority,
        "status": t.status, "aberto_em": _d(t.created_at.date()),
    } for t in Ticket.objects.filter(tenant=tenant).exclude(status__in=["fechado", "resolvido"]).order_by("-created_at")[:20]]


def _erp(tenant):
    from erp.models import Connector, EntitySyncState

    con = Connector.objects.filter(tenant=tenant, is_active=True).first()
    if not con:
        return None
    estados = EntitySyncState.objects.filter(connector=con).order_by("entity")
    ultima = max((s.last_ingest_at for s in estados if s.last_ingest_at), default=None)
    return {
        "erp": con.get_erp_display(), "agente_versao": con.agent_version or None,
        "ultima_carga": ultima.strftime("%Y-%m-%d %H:%M") if ultima else None,
        "tabelas_carregadas": [s.entity for s in estados if s.last_ingest_at],
    }


def tenant_results_context(tenant, year=None, user=None):
    """Contexto completo da empresa para o chat e as análises da IA."""
    year = year or date.today().year
    indicadores, ids = _indicadores(tenant, user)
    mapa, extra = _mapa(tenant)
    ctx = {
        "empresa": tenant.name,
        "hoje": date.today().isoformat(),
        "ano": year,
        "quem_pergunta": {"nome": user.first_name, "papel": user.role} if user is not None else None,
        "planejamento_estrategico": mapa,
        "diagnostico": _diagnostico(tenant, extra.get("mapa")),
        "indicadores": indicadores,
        "desvios_abertos": _desvios(tenant, ids),
        "planos_de_acao": _planos(tenant),
        "agenda_de_gestao": _agenda(tenant),
        "chamados_abertos": _chamados(tenant),
    }
    try:
        ctx["conector_erp"] = _erp(tenant)
    except Exception:
        ctx["conector_erp"] = None
    return ctx
