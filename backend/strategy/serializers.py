from rest_framework import serializers

from .models import CanvasItem, Goal, Meeting, Perspective, Stakeholder, StrategicMap, StrategicObjective, SwotItem


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
            "id", "name", "year_start", "year_end", "purpose", "mission", "vision",
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


# ---------------------------------------------------------------- diagnóstico e identidade

class _MapaDoTenant:
    def validate_map(self, value):
        tenant = self.context.get("tenant")
        if tenant and value.tenant_id != tenant.id:
            raise serializers.ValidationError("Mapa de outra empresa.")
        return value


class SwotItemSerializer(_MapaDoTenant, serializers.ModelSerializer):
    quadrant_label = serializers.CharField(source="get_quadrant_display", read_only=True)
    objective_name = serializers.CharField(source="objective.name", read_only=True, default="")

    class Meta:
        model = SwotItem
        fields = ["id", "map", "quadrant", "quadrant_label", "text", "detail", "impact", "objective", "objective_name", "order"]
        extra_kwargs = {"map": {"required": False}}

    def validate_impact(self, v):
        if not 1 <= int(v) <= 5:
            raise serializers.ValidationError("Impacto de 1 a 5.")
        return v


class CanvasItemSerializer(_MapaDoTenant, serializers.ModelSerializer):
    block_label = serializers.CharField(source="get_block_display", read_only=True)

    class Meta:
        model = CanvasItem
        fields = ["id", "map", "block", "block_label", "text", "order"]
        extra_kwargs = {"map": {"required": False}}


class StakeholderSerializer(serializers.ModelSerializer):
    strategy = serializers.CharField(read_only=True)
    org_unit_name = serializers.CharField(source="org_unit.name", read_only=True, default="")
    user_name = serializers.CharField(source="user.get_full_name", read_only=True, default="")

    class Meta:
        model = Stakeholder
        fields = [
            "id", "name", "kind", "organization", "role", "email", "phone", "influence", "interest",
            "expectations", "user", "user_name", "org_unit", "org_unit_name", "is_active", "strategy",
        ]

    def _faixa(self, v):
        if not 1 <= int(v) <= 5:
            raise serializers.ValidationError("De 1 a 5.")
        return v

    validate_influence = _faixa
    validate_interest = _faixa


class MeetingSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    organizer_name = serializers.CharField(source="organizer.get_full_name", read_only=True, default="")
    org_unit_name = serializers.CharField(source="org_unit.name", read_only=True, default="")
    participant_names = serializers.SerializerMethodField()
    stakeholder_names = serializers.SerializerMethodField()
    indicator_codes = serializers.SerializerMethodField()

    class Meta:
        model = Meeting
        fields = [
            "id", "title", "kind", "kind_label", "status", "status_label", "starts_at", "ends_at", "location",
            "org_unit", "org_unit_name", "organizer", "organizer_name", "participants", "participant_names",
            "stakeholders", "stakeholder_names", "indicators", "indicator_codes", "agenda", "minutes", "decisions",
        ]

    def get_participant_names(self, obj):
        return [u.get_full_name() or u.email for u in obj.participants.all()]

    def get_stakeholder_names(self, obj):
        return [s.name for s in obj.stakeholders.all()]

    def get_indicator_codes(self, obj):
        return [i.code for i in obj.indicators.all()]
