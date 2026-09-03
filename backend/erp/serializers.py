from rest_framework import serializers

from .models import AgentCommand, Connector, ConnectorLog, EntitySyncState


class ConnectorSerializer(serializers.ModelSerializer):
    online = serializers.BooleanField(read_only=True)
    agent_version = serializers.CharField(read_only=True)
    tenant_name = serializers.CharField(source="tenant.name", read_only=True)

    class Meta:
        model = Connector
        fields = [
            "id", "name", "erp", "perfil", "ingest_token", "config", "health",
            "last_seen_at", "is_active", "online", "agent_version", "tenant_name",
            "created_at",
        ]
        read_only_fields = ["ingest_token", "health", "last_seen_at"]


class ConnectorLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConnectorLog
        fields = ["id", "kind", "summary", "data", "created_at"]


class EntitySyncStateSerializer(serializers.ModelSerializer):
    class Meta:
        model = EntitySyncState
        fields = [
            "entity", "last_ingest_at", "rows_received", "rows_imported",
            "total_imported", "last_error",
        ]


class AgentCommandSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentCommand
        fields = [
            "id", "command", "payload", "status", "result", "error",
            "created_at", "leased_at", "finished_at",
        ]
        read_only_fields = ["status", "result", "error", "leased_at", "finished_at"]
