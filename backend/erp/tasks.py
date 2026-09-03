import logging
from datetime import date

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def calcular_indicadores_erp(tenant_id=None, indicator_id=None, meses=None):
    """Recalcula, a partir do espelho do ERP, todo indicador ligado a uma métrica.

    Grava IndicatorValue(source=agent) para cada mês do ano corrente (ou os
    últimos `meses`). O mês corrente é medido até hoje. Roda por beat (a cada
    30 min), depois de cada carga relevante e sob demanda pelo botão da tela.
    """
    from indicators.models import Indicator, IndicatorValue

    from .metrics import compute_metric, get_metric

    qs = Indicator.objects.filter(is_active=True).exclude(erp_metric="")
    if tenant_id:
        qs = qs.filter(tenant_id=tenant_id)
    if indicator_id:
        qs = qs.filter(id=indicator_id)

    hoje = date.today()
    if meses:
        periodos = []
        y, m = hoje.year, hoje.month
        for _ in range(int(meses)):
            periodos.append(date(y, m, 1))
            m -= 1
            if m == 0:
                y, m = y - 1, 12
        periodos.reverse()
    else:
        periodos = [date(hoje.year, m, 1) for m in range(1, hoje.month + 1)]

    from .sync import ENTITY_MODELS

    # Espelho vazio não é "zero": antes de o agente subir dados, o indicador
    # fica sem valor. Sem isto, contas a receber vencidas = 0 virava farol verde
    # e clientes positivados = 0 virava vermelho — em empresa sem carga nenhuma.
    tem_dados = {}

    def entidade_carregada(tenant_id, entity):
        key = (tenant_id, entity)
        if key not in tem_dados:
            model = ENTITY_MODELS.get(entity)
            tem_dados[key] = bool(model) and model.objects.filter(tenant_id=tenant_id).exists()
        return tem_dados[key]

    gravados = 0
    for indicator in qs.select_related("tenant"):
        metric = get_metric(indicator.erp_metric)
        if metric is None:
            continue
        if not all(entidade_carregada(indicator.tenant_id, e) for e in metric.entities):
            continue
        for periodo in periodos:
            try:
                valor = compute_metric(indicator.erp_metric, indicator.tenant, periodo, indicator.erp_filters)
            except Exception as exc:  # noqa: BLE001 — um KPI não derruba os demais
                logger.warning("métrica %s do indicador %s falhou: %s", indicator.erp_metric, indicator.code, exc)
                continue
            if valor is None:
                continue
            IndicatorValue.objects.update_or_create(
                indicator=indicator, period=periodo,
                defaults={
                    "value": valor,
                    "source": IndicatorValue.Source.AGENT,
                    "note": f"Calculado do ERP ({metric.label})",
                },
            )
            gravados += 1
    logger.info("calcular_indicadores_erp: %s valores gravados", gravados)
    return gravados


@shared_task
def sincronizar_metas_erp(tenant_id=None, indicator_id=None, meses=12):
    """Grava a meta mensal dos indicadores com `erp_target` a partir do espelho.

    Só toca meses em que o ERP tem meta; depois recalcula o farol dos valores
    já lançados. Roda por beat (a cada 6 h), após a carga de metas e sob demanda.
    """
    from indicators.models import Indicator, IndicatorTarget
    from indicators.services import recompute_indicator

    from .sync import ENTITY_MODELS
    from .targets import get_target_source, meta_do_erp

    qs = Indicator.objects.filter(is_active=True).exclude(erp_target="")
    if tenant_id:
        qs = qs.filter(tenant_id=tenant_id)
    if indicator_id:
        qs = qs.filter(id=indicator_id)

    hoje = date.today()
    periodos = []
    y, m = hoje.year, hoje.month
    for _ in range(int(meses)):
        periodos.append(date(y, m, 1))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    # Meses futuros do ano corrente também: meta digitada à mão (ou do seed)
    # não pode sobreviver escondida num indicador cuja meta vem do ERP.
    periodos += [date(hoje.year, mm, 1) for mm in range(hoje.month + 1, 13)]

    gravadas = 0
    for indicator in qs.select_related("tenant"):
        src = get_target_source(indicator.erp_target)
        if src is None:
            continue
        if not all(ENTITY_MODELS[e].objects.filter(tenant_id=indicator.tenant_id).exists() for e in src.entities if e in ENTITY_MODELS):
            continue
        mudou = False
        for periodo in periodos:
            try:
                meta = meta_do_erp(indicator.erp_target, indicator.tenant, periodo, indicator.erp_filters)
            except Exception as exc:  # noqa: BLE001
                logger.warning("meta %s do indicador %s falhou: %s", indicator.erp_target, indicator.code, exc)
                continue
            if meta is None:
                # Mês sem meta no ERP: não fica meta "à mão" escondida por baixo.
                apagadas, _ = IndicatorTarget.objects.filter(indicator=indicator, period=periodo).delete()
                mudou = mudou or bool(apagadas)
                continue
            IndicatorTarget.objects.update_or_create(
                indicator=indicator, period=periodo, defaults={"target_value": meta}
            )
            mudou = True
            gravadas += 1
        if mudou:
            recompute_indicator(indicator)
    logger.info("sincronizar_metas_erp: %s metas gravadas", gravadas)
    return gravadas


@shared_task
def purgar_logs_antigos(dias=30):
    from datetime import timedelta

    from django.utils import timezone

    from .models import AgentCommand, ConnectorLog

    limite = timezone.now() - timedelta(days=dias)
    n1, _ = ConnectorLog.objects.filter(created_at__lt=limite).delete()
    n2, _ = AgentCommand.objects.filter(created_at__lt=limite).delete()
    return n1 + n2
