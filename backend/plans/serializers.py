from rest_framework import serializers

from .models import ActionPlanUpdate, ActionItem, ActionPlan, Deviation


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
    plan_title = serializers.CharField(source="plan.title", read_only=True)
    plan_priority = serializers.CharField(source="plan.priority", read_only=True)
    progress = serializers.IntegerField(read_only=True)
    children_total = serializers.SerializerMethodField()
    children_done = serializers.SerializerMethodField()

    class Meta:
        model = ActionItem
        fields = [
            "id", "plan", "plan_title", "plan_priority", "parent", "title", "description", "priority", "blocked_reason",
            "responsible", "responsible_name", "due_date", "status", "order", "progress_pct", "progress",
            "children_total", "children_done", "created_at", "started_at", "done_at",
        ]
        read_only_fields = ["done_at", "started_at", "created_at"]

    def get_children_total(self, obj):
        return obj.children.count()

    def get_children_done(self, obj):
        return obj.children.filter(status=ActionItem.Status.FEITO).count()

    def validate_progress_pct(self, v):
        if v is not None and not 0 <= int(v) <= 100:
            raise serializers.ValidationError("De 0 a 100.")
        return v

    def validate(self, data):
        parent = data.get("parent") or (self.instance.parent if self.instance else None)
        plan = data.get("plan") or (self.instance.plan if self.instance else None)
        if parent is not None:
            if plan is not None and parent.plan_id != plan.id:
                raise serializers.ValidationError({"parent": "A atividade pai tem de ser do mesmo plano."})
            if parent.parent_id is not None:
                raise serializers.ValidationError({"parent": "Só um nível de subatividade."})
            if self.instance and parent.id == self.instance.id:
                raise serializers.ValidationError({"parent": "Uma atividade não pode ser filha de si mesma."})
        return data


class ActionPlanUpdateSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()

    class Meta:
        model = ActionPlanUpdate
        fields = ["id", "plan", "author", "author_name", "text", "progress_pct", "next_action", "created_at"]
        read_only_fields = ["plan", "author", "created_at"]

    def get_author_name(self, obj):
        return (obj.author.get_full_name() or obj.author.email) if obj.author else ""

    def validate_progress_pct(self, v):
        if v is not None and not 0 <= int(v) <= 100:
            raise serializers.ValidationError("De 0 a 100.")
        return v


class ActionPlanSerializer(serializers.ModelSerializer):
    who_name = serializers.CharField(source="who.first_name", read_only=True)
    org_unit_name = serializers.CharField(source="org_unit.name", read_only=True)
    indicator_code = serializers.CharField(source="indicator.code", read_only=True)
    items = ActionItemSerializer(many=True, read_only=True)
    items_done = serializers.SerializerMethodField()
    items_total = serializers.SerializerMethodField()
    progress_pct = serializers.SerializerMethodField()
    last_update_at = serializers.SerializerMethodField()
    last_update_text = serializers.SerializerMethodField()
    last_next_action = serializers.SerializerMethodField()

    class Meta:
        model = ActionPlan
        fields = [
            "id", "title", "what", "why", "where", "who", "who_name",
            "when_start", "when_end", "how", "how_much", "status", "pdca_stage",
            "origin", "deviation", "objective", "indicator", "indicator_code",
            "org_unit", "org_unit_name", "priority", "items", "items_done",
            "items_total", "progress_pct", "last_update_at", "last_update_text", "last_next_action", "created_at",
        ]

    def get_items_done(self, obj):
        return sum(1 for i in obj.items.all() if i.status == ActionItem.Status.FEITO)

    def get_items_total(self, obj):
        return obj.items.count()

    def get_progress_pct(self, obj):
        """Avanço do plano: média do avanço das atividades de primeiro nível (subatividades entram na mãe)."""
        raiz = [i for i in obj.items.all() if i.parent_id is None]
        if not raiz:
            return 0
        return round(sum(i.progress for i in raiz) / len(raiz))

    def _ultima(self, obj):
        return obj.updates.order_by("-created_at").first()

    def get_last_update_at(self, obj):
        u = self._ultima(obj)
        return u.created_at if u else None

    def get_last_update_text(self, obj):
        u = self._ultima(obj)
        return u.text if u else ""

    def get_last_next_action(self, obj):
        u = self._ultima(obj)
        return u.next_action if u else ""

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
