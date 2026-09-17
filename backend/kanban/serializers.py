from datetime import date

from rest_framework import serializers

from .models import Board, Task, TaskEvent, TaskMessage, TaskReply


def nome(user):
    if user is None:
        return ""
    return user.get_full_name() or user.first_name or user.email


class BoardSerializer(serializers.ModelSerializer):
    map_name = serializers.CharField(source="map.name", read_only=True, default="")
    tasks_count = serializers.IntegerField(source="tasks.count", read_only=True)

    class Meta:
        model = Board
        fields = ["id", "name", "description", "map", "map_name", "start_date", "end_date", "is_active", "tasks_count"]

    def validate_map(self, value):
        tenant = self.context.get("tenant")
        if value is not None and tenant and value.tenant_id != tenant.id:
            raise serializers.ValidationError("Planejamento de outra empresa.")
        return value

    def validate(self, data):
        ini = data.get("start_date", getattr(self.instance, "start_date", None))
        fim = data.get("end_date", getattr(self.instance, "end_date", None))
        if ini and fim and fim < ini:
            raise serializers.ValidationError({"end_date": "O fim não pode ser antes do início."})
        return data


class TaskEventSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()

    class Meta:
        model = TaskEvent
        fields = ["id", "author_name", "text", "created_at"]

    def get_author_name(self, obj):
        return nome(obj.author)


class TaskReplySerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()

    class Meta:
        model = TaskReply
        fields = ["id", "author", "author_name", "text", "created_at"]

    def get_author_name(self, obj):
        return nome(obj.author)


class TaskMessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.SerializerMethodField()
    recipient_name = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    task_title = serializers.CharField(source="task.title", read_only=True)
    task_status = serializers.CharField(source="task.status", read_only=True)
    board = serializers.IntegerField(source="task.board_id", read_only=True)
    replies = TaskReplySerializer(many=True, read_only=True)

    class Meta:
        model = TaskMessage
        fields = ["id", "task", "task_title", "task_status", "board", "sender", "sender_name", "recipient", "recipient_name",
                  "text", "status", "status_label", "replies", "created_at", "updated_at"]
        read_only_fields = ["task", "sender", "status", "created_at", "updated_at"]

    def get_sender_name(self, obj):
        return nome(obj.sender)

    def get_recipient_name(self, obj):
        return nome(obj.recipient)


class TaskSerializer(serializers.ModelSerializer):
    responsible_name = serializers.SerializerMethodField()
    watcher_names = serializers.SerializerMethodField()
    board_name = serializers.CharField(source="board.name", read_only=True)
    late = serializers.SerializerMethodField()
    days_late = serializers.SerializerMethodField()
    checklist_done = serializers.SerializerMethodField()
    open_messages = serializers.SerializerMethodField()

    class Meta:
        model = Task
        fields = ["id", "board", "board_name", "title", "description", "status", "priority", "responsible", "responsible_name",
                  "watchers", "watcher_names", "due_date", "checklist", "checklist_done", "order", "late", "days_late",
                  "open_messages", "created_at", "started_at", "done_at"]
        read_only_fields = ["created_at", "started_at", "done_at"]

    def get_responsible_name(self, obj):
        return nome(obj.responsible)

    def get_watcher_names(self, obj):
        return [nome(u) for u in obj.watchers.all()]

    def get_days_late(self, obj):
        if obj.due_date and obj.status != Task.Status.CONCLUIDO and obj.due_date < date.today():
            return (date.today() - obj.due_date).days
        return 0

    def get_late(self, obj):
        return self.get_days_late(obj) > 0

    def get_checklist_done(self, obj):
        return sum(1 for i in obj.checklist or [] if i.get("done"))

    def get_open_messages(self, obj):
        return sum(1 for m in obj.messages.all() if m.status != TaskMessage.Status.CONCLUIDA)

    def validate_checklist(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("Lista de itens.")
        limpa = []
        for item in value[:100]:
            texto = str((item or {}).get("text", "")).strip()[:250]
            if texto:
                limpa.append({"text": texto, "done": bool(item.get("done"))})
        return limpa

    def _da_empresa(self, users):
        tenant = self.context.get("tenant")
        for u in users:
            if u is not None and tenant and not u.belongs_to(tenant):
                raise serializers.ValidationError("Usuário de outra empresa.")

    def validate_responsible(self, value):
        self._da_empresa([value])
        return value

    def validate_watchers(self, value):
        self._da_empresa(value)
        return value

    def validate_board(self, value):
        tenant = self.context.get("tenant")
        if tenant and value.tenant_id != tenant.id:
            raise serializers.ValidationError("Board de outra empresa.")
        return value
