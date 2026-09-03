from rest_framework import serializers

from .models import Goal, Perspective, StrategicMap, StrategicObjective


class PerspectiveSerializer(serializers.ModelSerializer):
    objectives_count = serializers.IntegerField(source="objectives.count", read_only=True)

    class Meta:
        model = Perspective
        fields = ["id", "map", "name", "order", "color", "objectives_count"]
        extra_kwargs = {"map": {"required": False}}

    def validate_map(self, value):
        tenant = self.context.get("tenant")
        if tenant and value.tenant_id != tenant.id:
            raise serializers.ValidationError("Mapa de outra empresa.")
        return value


class StrategicObjectiveSerializer(serializers.ModelSerializer):
    owner_name = serializers.CharField(source="owner.first_name", read_only=True)
    perspective_name = serializers.CharField(source="perspective.name", read_only=True)

    class Meta:
        model = StrategicObjective
        fields = [
            "id", "perspective", "perspective_name", "name", "description",
            "owner", "owner_name", "order", "contributes_to", "pos_x", "pos_y",
        ]

    def validate_contributes_to(self, value):
        """Só liga objetivos da própria empresa — e nunca um objetivo a si mesmo."""
        tenant = self.context.get("tenant")
        for objective in value:
            if tenant and objective.tenant_id != tenant.id:
                raise serializers.ValidationError("Objetivo de outra empresa.")
            if self.instance and objective.pk == self.instance.pk:
                raise serializers.ValidationError("Um objetivo não pode contribuir para si mesmo.")
        return value


class ObjectiveNestedSerializer(StrategicObjectiveSerializer):
    indicators = serializers.SerializerMethodField()
    contributes_to = serializers.PrimaryKeyRelatedField(many=True, read_only=True)

    class Meta(StrategicObjectiveSerializer.Meta):
        fields = StrategicObjectiveSerializer.Meta.fields + ["indicators"]

    def get_indicators(self, obj):
        return [
            {
                "id": i.id,
                "code": i.code,
                "name": i.name,
                "last_status": last.status if (last := i.values.order_by("-period").first()) else None,
            }
            for i in obj.indicators.filter(is_active=True)
        ]


class PerspectiveNestedSerializer(PerspectiveSerializer):
    objectives = ObjectiveNestedSerializer(many=True, read_only=True)

    class Meta(PerspectiveSerializer.Meta):
        fields = PerspectiveSerializer.Meta.fields + ["objectives"]


class StrategicMapSerializer(serializers.ModelSerializer):
    class Meta:
        model = StrategicMap
        fields = [
            "id", "name", "year_start", "year_end", "mission", "vision",
            "values_text", "is_active",
        ]


class StrategicMapNestedSerializer(StrategicMapSerializer):
    perspectives = PerspectiveNestedSerializer(many=True, read_only=True)

    class Meta(StrategicMapSerializer.Meta):
        fields = StrategicMapSerializer.Meta.fields + ["perspectives"]


class GoalSerializer(serializers.ModelSerializer):
    owner_name = serializers.CharField(source="owner.first_name", read_only=True)
    org_unit_name = serializers.CharField(source="org_unit.name", read_only=True)
    objective_name = serializers.CharField(source="objective.name", read_only=True)
    indicator_status = serializers.SerializerMethodField()

    class Meta:
        model = Goal
        fields = [
            "id", "objective", "objective_name", "parent", "level", "org_unit",
            "org_unit_name", "owner", "owner_name", "name", "description",
            "indicator", "indicator_status", "weight", "status",
        ]

    def get_indicator_status(self, obj):
        if not obj.indicator_id:
            return None
        last = obj.indicator.values.order_by("-period").first()
        return last.status if last else None

    def _check_same_tenant(self, value, msg):
        tenant = self.context.get("tenant")
        if value is not None and tenant and value.tenant_id != tenant.id:
            raise serializers.ValidationError(msg)
        return value

    def validate_parent(self, value):
        return self._check_same_tenant(value, "Meta pai de outra empresa.")

    def validate_objective(self, value):
        return self._check_same_tenant(value, "Objetivo de outra empresa.")

    def validate_indicator(self, value):
        return self._check_same_tenant(value, "Indicador de outra empresa.")

    def validate_org_unit(self, value):
        return self._check_same_tenant(value, "Unidade de outra empresa.")
