from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import User

ROLE_ORDER = {
    User.Role.COLABORADOR: 0,
    User.Role.GESTOR: 1,
    User.Role.ADMIN: 2,
    User.Role.ROOT: 3,
}


def role_at_least(user, role):
    return ROLE_ORDER.get(user.role, -1) >= ROLE_ORDER[role]


class IsRoot(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == User.Role.ROOT


class IsTenantAdmin(BasePermission):
    """Escrita: admin do tenant (ou root). Leitura: qualquer autenticado."""

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return True
        return role_at_least(request.user, User.Role.ADMIN)


class IsTenantAdminStrict(BasePermission):
    """Leitura E escrita só para admin do tenant (ou root). Usado onde até ver é
    sensível — ex.: conector do ERP (chave, comandos, dados brutos da carga)."""

    def has_permission(self, request, view):
        return request.user.is_authenticated and role_at_least(request.user, User.Role.ADMIN)


class IsGestorStrict(BasePermission):
    """Leitura E escrita só para gestor, admin ou root — telas gerenciais (BI do ERP)."""

    def has_permission(self, request, view):
        return request.user.is_authenticated and role_at_least(request.user, User.Role.GESTOR)


class IsGestorOrAbove(BasePermission):
    """Escrita: gestor, admin ou root. Leitura: qualquer autenticado."""

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return True
        return role_at_least(request.user, User.Role.GESTOR)
