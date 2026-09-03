from rest_framework import serializers

from .models import DataSource, Indicator, IndicatorTarget, IndicatorValue


class DataSourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataSource
        fields = ["id", "name", "type", "config", "is_active"]


class IndicatorTargetSerializer(serializers.ModelSerializer):
    class Meta:
        model = IndicatorTarget
        fields = ["id", "indicator", "period", "target_value"]


class IndicatorValueSerializer(serializers.ModelSerializer):
    entered_by_name = serializers.CharField(source="entered_by.first_name", read_only=True)

    class Meta:
        model = IndicatorValue
        fields = [
            "id", "indicator", "period", "value", "entered_by", "entered_by_name",
            "source", "note", "achievement_pct", "status",
        ]
        read_only_fields = ["achievement_pct", "status", "entered_by"]


class IndicatorSerializer(serializers.ModelSerializer):
    org_unit_name = serializers.CharField(source="org_unit.name", read_only=True)
    owner_name = serializers.CharField(source="owner.first_name", read_only=True)
    objective_name = serializers.CharField(source="objective.name", read_only=True)
    last_value = serializers.SerializerMethodField()
    spark = serializers.SerializerMethodField()
    erp_metric_label = serializers.SerializerMethodField()

    class Meta:
        model = Indicator
        fields = [
            "id", "code", "name", "description", "unit", "decimals", "frequency",
            "polarity", "aggregation", "org_unit", "org_unit_name", "owner",
            "owner_name", "objective", "objective_name", "data_source",
            "erp_metric", "erp_metric_label", "erp_filters",
            "yellow_threshold_pct", "is_active", "last_value", "spark",
        ]

    def get_erp_metric_label(self, obj):
        if not obj.erp_metric:
            return None
        from erp.metrics import get_metric

        m = get_metric(obj.erp_metric)
        return m.label if m else obj.erp_metric

    def validate_erp_metric(self, value):
        if value:
            from erp.metrics import get_metric

            if get_metric(value) is None:
                raise serializers.ValidationError("Métrica do ERP desconhecida.")
        return value or ""

    def get_last_value(self, obj):
        last = obj.values.order_by("-period").first()
        if last is None:
            return None
        return {
            "period": last.period,
            "value": last.value,
            "achievement_pct": last.achievement_pct,
            "status": last.status,
        }

    def get_spark(self, obj):
        """Últimos 12 atingimentos, em ordem cronológica — alimenta o sparkline."""
        recent = list(obj.values.order_by("-period")[:12])
        return [v.achievement_pct for v in reversed(recent) if v.achievement_pct is not None]

    def _check_same_tenant(self, value, msg):
        tenant = self.context.get("tenant")
        if value is not None and tenant and value.tenant_id != tenant.id:
            raise serializers.ValidationError(msg)
        return value

    def validate_org_unit(self, value):
        return self._check_same_tenant(value, "Unidade de outra empresa.")

    def validate_objective(self, value):
        return self._check_same_tenant(value, "Objetivo de outra empresa.")

    def validate_data_source(self, value):
        return self._check_same_tenant(value, "Fonte de dados de outra empresa.")

    def validate(self, attrs):
        tenant = self.context.get("tenant")
        code = attrs.get("code") or (self.instance.code if self.instance else None)
        if tenant and code:
            qs = Indicator.objects.filter(tenant=tenant, code=code)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError({"code": "Já existe um indicador com este código."})
        return attrs
