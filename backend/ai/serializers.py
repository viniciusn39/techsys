from rest_framework import serializers

from .models import AIChatMessage, AIChatSession, AIInsight, AIIntegration


class AIIntegrationSerializer(serializers.ModelSerializer):
    api_key = serializers.CharField(write_only=True, required=False, allow_blank=True)
    api_key_set = serializers.BooleanField(read_only=True)

    class Meta:
        model = AIIntegration
        fields = [
            "id", "provider", "base_url", "model", "temperature", "max_tokens",
            "is_active", "api_key", "api_key_set", "last_test_at", "last_test_ok",
        ]
        read_only_fields = ["last_test_at", "last_test_ok"]

    def _apply_key(self, instance, api_key):
        if api_key:
            instance.set_api_key(api_key)
            instance.save(update_fields=["api_key_encrypted"])

    def create(self, validated_data):
        api_key = validated_data.pop("api_key", None)
        instance = super().create(validated_data)
        self._apply_key(instance, api_key)
        return instance

    def update(self, instance, validated_data):
        api_key = validated_data.pop("api_key", None)
        instance = super().update(instance, validated_data)
        self._apply_key(instance, api_key)
        return instance


class AIInsightSerializer(serializers.ModelSerializer):
    indicator_code = serializers.CharField(source="indicator.code", read_only=True)
    requested_by_name = serializers.CharField(source="requested_by.first_name", read_only=True)

    class Meta:
        model = AIInsight
        fields = [
            "id", "kind", "indicator", "indicator_code", "deviation", "period",
            "status", "content", "data", "error_message", "requested_by",
            "requested_by_name", "tokens_used", "created_at",
        ]
        read_only_fields = [
            "status", "content", "data", "error_message", "requested_by", "tokens_used",
        ]


class AIChatMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIChatMessage
        fields = ["id", "role", "content", "created_at"]


class AIChatSessionSerializer(serializers.ModelSerializer):
    messages = AIChatMessageSerializer(many=True, read_only=True)

    class Meta:
        model = AIChatSession
        fields = ["id", "title", "created_at", "updated_at", "messages"]
