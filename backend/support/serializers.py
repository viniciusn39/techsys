from rest_framework import serializers

from .models import Ticket, TicketMessage


class TicketMessageSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()

    class Meta:
        model = TicketMessage
        fields = ["id", "ticket", "author", "author_name", "body", "is_internal", "from_support", "created_at"]
        read_only_fields = ["ticket", "author", "from_support", "created_at"]

    def get_author_name(self, obj):
        if obj.author is None:
            return ""
        return obj.author.get_full_name() or obj.author.email


class TicketSerializer(serializers.ModelSerializer):
    opened_by_name = serializers.SerializerMethodField()
    assigned_to_name = serializers.SerializerMethodField()
    tenant_name = serializers.CharField(source="tenant.name", read_only=True)
    tenant_id = serializers.IntegerField(source="tenant.id", read_only=True)
    category_label = serializers.CharField(source="get_category_display", read_only=True)
    priority_label = serializers.CharField(source="get_priority_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    messages_count = serializers.IntegerField(source="messages.count", read_only=True)
    last_message_at = serializers.SerializerMethodField()

    class Meta:
        model = Ticket
        fields = [
            "id", "number", "title", "description", "category", "category_label", "priority", "priority_label",
            "status", "status_label", "module", "opened_by", "opened_by_name", "assigned_to", "assigned_to_name",
            "tenant_id", "tenant_name", "first_response_at", "resolved_at", "closed_at", "rating", "rating_comment",
            "messages_count", "last_message_at", "created_at", "updated_at",
        ]
        read_only_fields = ["number", "opened_by", "first_response_at", "resolved_at", "closed_at", "created_at", "updated_at"]

    def _nome(self, u):
        return (u.get_full_name() or u.email) if u else ""

    def get_opened_by_name(self, obj):
        return self._nome(obj.opened_by)

    def get_assigned_to_name(self, obj):
        return self._nome(obj.assigned_to)

    def get_last_message_at(self, obj):
        m = obj.messages.order_by("-created_at").first()
        return m.created_at if m else None

    def validate_rating(self, v):
        if v is not None and not 1 <= int(v) <= 5:
            raise serializers.ValidationError("Avaliação de 1 a 5.")
        return v


class TicketDetailSerializer(TicketSerializer):
    messages = serializers.SerializerMethodField()

    class Meta(TicketSerializer.Meta):
        fields = TicketSerializer.Meta.fields + ["messages"]

    def get_messages(self, obj):
        qs = obj.messages.select_related("author")
        user = self.context.get("request").user if self.context.get("request") else None
        if not (user and user.role == "root"):
            qs = qs.filter(is_internal=False)
        return TicketMessageSerializer(qs, many=True).data
