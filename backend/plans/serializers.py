from rest_framework import serializers

from .models import ActionItem, ActionPlan, Deviation


class DeviationSerializer(serializers.ModelSerializer):
    indicator_code = serializers.CharField(source="indicator.code", read_only=True)
    indicator_name = serializers.CharField(source="indicator.name", read_only=True)
    period = serializers.DateField(source="indicator_value.period", read_only=True)
    value = serializers.DecimalField(
        source="indicator_value.value", max_digits=18, decimal_places=4, read_only=True
    )
    achievement_pct = serializers.DecimalField(
        source="indicator_value.achievement_pct", max_digits=9, decimal_places=2, read_only=True
    )
    plans_count = serializers.IntegerField(source="action_plans.count", read_only=True)

    class Meta:
        model = Deviation
        fields = [
            "id", "indicator", "indicator_code", "indicator_name", "indicator_value",
            "period", "value", "achievement_pct", "status", "root_cause",
            "detected_at", "plans_count",
        ]
        read_only_fields = ["indicator", "indicator_value", "detected_at"]


class ActionItemSerializer(serializers.ModelSerializer):
    responsible_name = serializers.CharField(source="responsible.first_name", read_only=True)

    class Meta:
        model = ActionItem
        fields = [
            "id", "plan", "title", "responsible", "responsible_name",
            "due_date", "status", "order", "done_at",
        ]
        read_only_fields = ["done_at"]


class ActionPlanSerializer(serializers.ModelSerializer):
    who_name = serializers.CharField(source="who.first_name", read_only=True)
    org_unit_name = serializers.CharField(source="org_unit.name", read_only=True)
    indicator_code = serializers.CharField(source="indicator.code", read_only=True)
    items = ActionItemSerializer(many=True, read_only=True)
    items_done = serializers.SerializerMethodField()
    items_total = serializers.SerializerMethodField()

    class Meta:
        model = ActionPlan
        fields = [
            "id", "title", "what", "why", "where", "who", "who_name",
            "when_start", "when_end", "how", "how_much", "status", "pdca_stage",
            "origin", "deviation", "objective", "indicator", "indicator_code",
            "org_unit", "org_unit_name", "priority", "items", "items_done",
            "items_total", "created_at",
        ]

    def get_items_done(self, obj):
        return sum(1 for i in obj.items.all() if i.status == ActionItem.Status.FEITO)

    def get_items_total(self, obj):
        return obj.items.count()

    def _check_same_tenant(self, value, msg):
        tenant = self.context.get("tenant")
        if value is not None and tenant and value.tenant_id != tenant.id:
            raise serializers.ValidationError(msg)
        return value

    def validate_deviation(self, value):
        return self._check_same_tenant(value, "Desvio de outra empresa.")

    def validate_indicator(self, value):
        return self._check_same_tenant(value, "Indicador de outra empresa.")

    def validate_objective(self, value):
        return self._check_same_tenant(value, "Objetivo de outra empresa.")

    def validate_org_unit(self, value):
        return self._check_same_tenant(value, "Unidade de outra empresa.")
