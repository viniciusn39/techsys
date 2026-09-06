"""Acesso por setor (RBAC): o que cada usuário enxerga.

Regras:
  - root e admin veem tudo, sempre;
  - usuário sem perfil vê tudo que o papel permite (comportamento antigo);
  - perfil com `sectors` vazio = todos os setores; com `modules` vazio = todos os módulos;
  - indicador sem setor (manual, criado à mão) é visível a todos os perfis;
  - filtro de módulos vale para o menu; a API de indicadores aplica o filtro de setor.
"""
from django.db.models import Q

from .models import MODULOS, SETORES, User

TODOS_MODULOS = [k for k, _ in MODULOS]
TODOS_SETORES = [k for k, _ in SETORES]


def perfil(user):
    if not getattr(user, "is_authenticated", False):
        return None
    if user.role in (User.Role.ROOT, User.Role.ADMIN):
        return None
    return user.access_profile


def setores_permitidos(user):
    """None = todos."""
    p = perfil(user)
    if p is None or not p.sectors:
        return None
    return list(p.sectors)


def modulos_permitidos(user):
    """None = todos."""
    p = perfil(user)
    if p is None or not p.modules:
        return None
    return list(p.modules)


def filtrar_indicadores(user, qs):
    setores = setores_permitidos(user)
    if setores is None:
        return qs
    return qs.filter(Q(sector__in=setores) | Q(sector=""))
