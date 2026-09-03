from django.db import transaction
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from accounts.permissions import IsGestorOrAbove, IsTenantAdmin
from accounts.tenancy import TenantScopedViewSet, get_request_tenant
from indicators.models import Indicator

from .models import Goal, Perspective, StrategicMap, StrategicObjective
from .provisioning import create_default_perspectives
from .serializers import (
    GoalSerializer,
    PerspectiveSerializer,
    StrategicMapNestedSerializer,
    StrategicMapSerializer,
    StrategicObjectiveSerializer,
)


class StrategicMapViewSet(TenantScopedViewSet):
    queryset = StrategicMap.objects.all()
    serializer_class = StrategicMapSerializer
    permission_classes = [IsTenantAdmin]

    def perform_create(self, serializer):
        super().perform_create(serializer)
        create_default_perspectives(serializer.instance)

    @action(detail=True, methods=["post"], url_path="apply-suggestion")
    def apply_suggestion(self, request, pk=None):
        """Materializa no mapa a sugestão de IA que o usuário aceitou.

        Recebe a lista já filtrada pelo usuário; cria os objetivos que ainda não
        existem (por nome) e liga as setas de causa e efeito. Tudo ou nada.
        """
        smap = self.get_object()
        tenant = self.get_tenant()
        perspectives = {p.name: p for p in smap.perspectives.all()}

        objectives_in = request.data.get("objectives") or []
        links_in = request.data.get("links") or []
        if not objectives_in:
            raise ValidationError("Nenhum objetivo selecionado.")

        indicators = {
            i.code: i for i in Indicator.objects.filter(tenant=tenant, is_active=True)
        }

        with transaction.atomic():
            by_name = {
                o.name: o
                for o in StrategicObjective.objects.filter(
                    tenant=tenant, perspective__map=smap
                )
            }
            created = []
            for item in objectives_in:
                perspective = perspectives.get(item.get("perspective"))
                name = (item.get("name") or "").strip()
                if perspective is None or not name or name in by_name:
                    continue
                objective = StrategicObjective.objects.create(
                    tenant=tenant,
                    perspective=perspective,
                    name=name[:200],
                    description=item.get("description") or "",
                    order=perspective.objectives.count(),
                )
                by_name[name] = objective
                created.append(objective)

                # Vincula o indicador sugerido, se ele existir e estiver livre.
                indicator = indicators.get(item.get("indicator_code"))
                if indicator is not None and indicator.objective_id is None:
                    indicator.objective = objective
                    indicator.save(update_fields=["objective"])

            linked = 0
            for link in links_in:
                source = by_name.get(link.get("from"))
                target = by_name.get(link.get("to"))
                if source and target and source.pk != target.pk:
                    source.contributes_to.add(target)
                    linked += 1

        return Response(
            {
                "created": len(created),
                "linked": linked,
                "map": StrategicMapNestedSerializer(smap).data,
            },
            status=201,
        )

    @action(detail=False, methods=["get"])
    def active(self, request):
        smap = (
            self.get_queryset()
            .filter(is_active=True)
            .prefetch_related("perspectives__objectives__indicators")
            .first()
        )
        if smap is None:
            return Response(None)
        return Response(StrategicMapNestedSerializer(smap).data)


class PerspectiveViewSet(viewsets.ModelViewSet):
    """Perspectivas do mapa — dados editáveis, não uma lista fixa no código."""

    queryset = Perspective.objects.all()
    serializer_class = PerspectiveSerializer
    permission_classes = [IsTenantAdmin]
    pagination_class = None
    filterset_fields = ["map"]

    def get_queryset(self):
        tenant = get_request_tenant(self.request)
        if tenant is None:
            return self.queryset.none()
        return self.queryset.filter(map__tenant=tenant)

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["tenant"] = get_request_tenant(self.request)
        return ctx

    def perform_create(self, serializer):
        tenant = get_request_tenant(self.request)
        if tenant is None:
            raise PermissionDenied("Nenhuma empresa selecionada.")

        # Sem mapa explícito, entra no mapa ativo da empresa.
        smap = serializer.validated_data.get("map")
        if smap is None:
            smap = StrategicMap.objects.filter(tenant=tenant, is_active=True).first()
            if smap is None:
                raise ValidationError("A empresa ainda não tem um mapa estratégico ativo.")
        elif smap.tenant_id != tenant.id:
            raise PermissionDenied("Mapa de outra empresa.")

        last = smap.perspectives.order_by("-order").first()
        serializer.save(map=smap, order=(last.order + 1) if last else 0)

    @action(detail=True, methods=["patch"])
    def move(self, request, pk=None):
        """Troca a ordem com a perspectiva vizinha (cima/baixo)."""
        perspective = self.get_object()
        direction = request.data.get("direction")
        if direction not in ("up", "down"):
            raise ValidationError({"direction": 'Use "up" ou "down".'})

        siblings = list(perspective.map.perspectives.order_by("order", "id"))
        index = siblings.index(perspective)
        target = index - 1 if direction == "up" else index + 1
        if 0 <= target < len(siblings):
            other = siblings[target]
            siblings[index], siblings[target] = siblings[target], siblings[index]
            for position, item in enumerate(siblings):
                if item.order != position:
                    item.order = position
                    item.save(update_fields=["order"])

        return Response(
            PerspectiveSerializer(
                perspective.map.perspectives.order_by("order", "id"),
                many=True,
                context=self.get_serializer_context(),
            ).data
        )


class StrategicObjectiveViewSet(TenantScopedViewSet):
    queryset = StrategicObjective.objects.select_related("perspective", "owner")
    serializer_class = StrategicObjectiveSerializer
    permission_classes = [IsGestorOrAbove]
    filterset_fields = ["perspective"]
    pagination_class = None

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["tenant"] = self.get_tenant()
        return ctx

    def perform_create(self, serializer):
        tenant = self.get_tenant()
        if tenant is None:
            raise PermissionDenied("Nenhuma empresa selecionada.")
        perspective = serializer.validated_data["perspective"]
        if perspective.map.tenant_id != tenant.id:
            raise PermissionDenied("Perspectiva de outra empresa.")
        serializer.save(tenant=tenant)

    @action(detail=False, methods=["post"])
    def layout(self, request):
        """Salva as posições do diagrama (arrastar e soltar).

        Aceita também troca de perspectiva: arrastar um objetivo para outra faixa
        muda a que ele pertence.
        """
        qs = self.get_queryset()
        by_id = {o.id: o for o in qs}
        perspectives = {
            p.id: p for p in Perspective.objects.filter(map__tenant=self.get_tenant())
        }

        updated = []
        for item in request.data.get("positions", []):
            objective = by_id.get(item.get("id"))
            if objective is None:
                continue
            objective.pos_x = item.get("pos_x")
            objective.pos_y = item.get("pos_y")
            fields = ["pos_x", "pos_y"]

            new_perspective = perspectives.get(item.get("perspective"))
            if new_perspective and new_perspective.id != objective.perspective_id:
                objective.perspective = new_perspective
                fields.append("perspective")

            objective.save(update_fields=fields)
            updated.append(objective)

        return Response(
            StrategicObjectiveSerializer(
                updated, many=True, context=self.get_serializer_context()
            ).data
        )

    @action(detail=True, methods=["post"], url_path="toggle-link")
    def toggle_link(self, request, pk=None):
        """Liga/desliga a seta de causa-efeito deste objetivo para outro."""
        source = self.get_object()
        target = self.get_queryset().filter(pk=request.data.get("target")).first()
        if target is None:
            raise ValidationError({"target": "Objetivo de destino não encontrado."})
        if target.pk == source.pk:
            raise ValidationError({"target": "Um objetivo não pode contribuir para si mesmo."})

        if source.contributes_to.filter(pk=target.pk).exists():
            source.contributes_to.remove(target)
            linked = False
        else:
            source.contributes_to.add(target)
            linked = True
        return Response({"linked": linked, "source": source.pk, "target": target.pk})


class GoalViewSet(TenantScopedViewSet):
    queryset = Goal.objects.select_related("owner", "org_unit", "objective", "indicator")
    serializer_class = GoalSerializer
    permission_classes = [IsGestorOrAbove]
    filterset_fields = ["objective", "level", "org_unit", "status"]
    pagination_class = None

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["tenant"] = self.get_tenant()
        return ctx

    @action(detail=False, methods=["get"])
    def tree(self, request):
        qs = self.filter_queryset(self.get_queryset())
        goals = list(qs)
        by_parent = {}
        for g in goals:
            by_parent.setdefault(g.parent_id, []).append(g)
        ids = {g.id for g in goals}

        def build(parent_id):
            return [
                {**GoalSerializer(g, context=self.get_serializer_context()).data,
                 "children": build(g.id)}
                for g in by_parent.get(parent_id, [])
            ]

        roots = [g for g in goals if g.parent_id is None or g.parent_id not in ids]
        return Response(
            [
                {**GoalSerializer(g, context=self.get_serializer_context()).data,
                 "children": build(g.id)}
                for g in roots
            ]
        )
