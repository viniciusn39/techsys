"""Planejamento em uso na requisição.

Uma empresa pode ter vários planejamentos. O frontend manda o escolhido no header
X-Map-Id; sem ele (ou se não for da empresa) vale o ativo mais recente e, na falta
de um ativo, o mais recente de todos.
"""
from .models import StrategicMap


def mapa_padrao(tenant):
    qs = StrategicMap.objects.filter(tenant=tenant)
    return qs.filter(is_active=True).order_by("-year_start", "-id").first() or qs.order_by("-year_start", "-id").first()


def mapa_atual(request, tenant):
    if tenant is None:
        return None
    map_id = request.headers.get("X-Map-Id") if request is not None else None
    if map_id and str(map_id).isdigit():
        escolhido = StrategicMap.objects.filter(tenant=tenant, pk=map_id).first()
        if escolhido is not None:
            return escolhido
    return mapa_padrao(tenant)
