import logging

from celery import shared_task

logger = logging.getLogger(__name__)


def _parse_json_reply(raw):
    """A IA às vezes embrulha o JSON em ```json ... ``` — extrai o objeto."""
    import json
    import re

    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("A resposta não contém um objeto JSON.")
    return json.loads(text[start : end + 1])


@shared_task
def gerar_insight(insight_id):
    from .context import indicator_series
    from .models import AIInsight
    from .prompts import (
        SYSTEM_PROMPT,
        prompt_analise_desvio,
        prompt_analise_indicador,
        prompt_sugestao_mapa,
    )
    from .providers.base import AIProviderError
    from .providers.factory import get_provider

    insight = AIInsight.objects.filter(id=insight_id).first()
    if insight is None:
        return

    insight.status = AIInsight.Status.PROCESSANDO
    insight.save(update_fields=["status"])

    try:
        if insight.kind == AIInsight.Kind.SUGESTAO_MAPA:
            from indicators.models import Indicator
            from strategy.models import StrategicMap

            smap = StrategicMap.objects.filter(
                tenant=insight.tenant, is_active=True
            ).prefetch_related("perspectives").first()
            if smap is None:
                raise AIProviderError("A empresa não tem um mapa estratégico ativo.")

            perspectives = [p.name for p in smap.perspectives.all()]
            indicators = [
                {"codigo": i.code, "nome": i.name, "unidade": i.unit}
                for i in Indicator.objects.filter(tenant=insight.tenant, is_active=True)
            ]
            user_prompt = prompt_sugestao_mapa(insight.tenant, smap, perspectives, indicators)

            provider = get_provider()
            result = provider.chat([
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ])
            try:
                payload = _parse_json_reply(result.content)
            except ValueError as exc:
                raise AIProviderError(f"A IA não devolveu JSON válido: {exc}") from exc

            # Descarta objetivos em perspectivas que não existem e ligações soltas.
            valid = [
                o for o in payload.get("objectives", [])
                if o.get("perspective") in perspectives and o.get("name")
            ]
            names = {o["name"] for o in valid}
            links = [
                l for l in payload.get("links", [])
                if l.get("from") in names and l.get("to") in names and l["from"] != l["to"]
            ]

            insight.data = {"objectives": valid, "links": links}
            insight.content = f"{len(valid)} objetivos e {len(links)} ligações sugeridos."
            insight.tokens_used = result.tokens_used
            insight.status = AIInsight.Status.CONCLUIDO
            insight.error_message = ""
            insight.save()
            return

        if insight.kind == AIInsight.Kind.ANALISE_DESVIO and insight.deviation:
            deviation = insight.deviation
            series = indicator_series(deviation.indicator)
            plans = [
                {"titulo": p.title, "status": p.status, "pdca": p.pdca_stage}
                for p in deviation.action_plans.all()
            ]
            user_prompt = prompt_analise_desvio(deviation, series, plans)
        elif insight.indicator:
            from indicators.services import compute_ytd
            from datetime import date

            year = insight.period.year if insight.period else date.today().year
            series = indicator_series(insight.indicator, year)
            ytd = compute_ytd(insight.indicator, year)
            user_prompt = prompt_analise_indicador(insight.indicator, series, ytd)
        else:
            raise AIProviderError("Insight sem indicador/desvio associado.")

        provider = get_provider()
        result = provider.chat([
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ])
        insight.content = result.content
        insight.tokens_used = result.tokens_used
        insight.status = AIInsight.Status.CONCLUIDO
        insight.error_message = ""
    except AIProviderError as exc:
        insight.status = AIInsight.Status.ERRO
        insight.error_message = str(exc)
        logger.warning("gerar_insight %s falhou: %s", insight_id, exc)
    except Exception as exc:  # noqa: BLE001 — task não pode morrer sem registrar o erro
        insight.status = AIInsight.Status.ERRO
        insight.error_message = f"Erro inesperado: {exc}"
        logger.exception("gerar_insight %s erro inesperado", insight_id)

    insight.save()
