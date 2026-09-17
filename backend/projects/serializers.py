from rest_framework import serializers

from .models import ActivityFca, Project, ProjectActivity


def _nome(user):
    if user is None:
        return ""
    return user.get_full_name() or user.first_name or user.email


class ProjectSerializer(serializers.ModelSerializer):
    owner_name = serializers.SerializerMethodField()
    org_unit_name = serializers.CharField(source="org_unit.name", read_only=True, default="")
    map_name = serializers.CharField(source="map.name", read_only=True, default="")
    # Números da EAP: a view calcula uma vez por requisição e entrega em context["resumos"].
    activities_count = serializers.SerializerMethodField()
    subactivities_count = serializers.SerializerMethodField()
    done_count = serializers.SerializerMethodField()
    late_count = serializers.SerializerMethodField()
    progress = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = [
            "id", "code", "map", "map_name", "title", "description", "owner", "owner_name",
            "org_unit", "org_unit_name", "start_date", "end_date", "status",
            "partners", "swot_items", "objectives",
            "activities_count", "subactivities_count", "done_count", "late_count", "progress", "created_at",
        ]
        read_only_fields = ["code", "created_at"]

    def get_owner_name(self, obj):
        return _nome(obj.owner)

    def _resumo(self, obj, chave):
        return (self.context.get("resumos") or {}).get(obj.id, {}).get(chave, 0)

    def get_activities_count(self, obj):
        return self._resumo(obj, "activities_count")

    def get_subactivities_count(self, obj):
        return self._resumo(obj, "subactivities_count")

    def get_done_count(self, obj):
        return self._resumo(obj, "done_count")

    def get_late_count(self, obj):
        return self._resumo(obj, "late_count")

    def get_progress(self, obj):
        return self._resumo(obj, "progress")

    def _do_tenant(self, objs, msg):
        tenant = self.context.get("tenant")
        for o in objs:
            if o is not None and tenant and o.tenant_id != tenant.id:
                raise serializers.ValidationError(msg)

    def validate_map(self, value):
        self._do_tenant([value], "Planejamento de outra empresa.")
        return value

    def validate_owner(self, value):
        self._do_tenant([value], "Usuário de outra empresa.")
        return value

    def validate_org_unit(self, value):
        self._do_tenant([value], "Departamento de outra empresa.")
        return value

    def validate_partners(self, value):
        self._do_tenant(value, "Usuário de outra empresa.")
        return value

    def validate_swot_items(self, value):
        self._do_tenant(value, "Item da SWOT de outra empresa.")
        return value

    def validate_objectives(self, value):
        self._do_tenant(value, "Objetivo de outra empresa.")
        return value

    def validate(self, data):
        inicio = data.get("start_date") or (self.instance.start_date if self.instance else None)
        fim = data.get("end_date") or (self.instance.end_date if self.instance else None)
        if inicio and fim and fim < inicio:
            raise serializers.ValidationError({"end_date": "A data final não pode ser antes do início."})
        return data


class ProjectActivitySerializer(serializers.ModelSerializer):
    responsible_name = serializers.SerializerMethodField()
    phase_label = serializers.CharField(source="get_phase_display", read_only=True)

    class Meta:
        model = ProjectActivity
        fields = [
            "id", "project", "parent", "title", "description", "responsible", "responsible_name",
            "phase", "phase_label", "start_date", "end_date", "status", "progress_pct", "notes",
            "order", "created_at", "done_at",
        ]
        read_only_fields = ["created_at", "done_at"]

    def get_responsible_name(self, obj):
        return _nome(obj.responsible)

    def validate_progress_pct(self, v):
        if not 0 <= int(v) <= 100:
            raise serializers.ValidationError("De 0 a 100.")
        return v

    def validate(self, data):
        project = data.get("project") or (self.instance.project if self.instance else None)
        parent = data.get("parent", self.instance.parent if self.instance else None)
        if self.instance and "project" in data and data["project"].id != self.instance.project_id:
            raise serializers.ValidationError({"project": "A atividade não muda de projeto."})
        if parent is not None:
            if project is not None and parent.project_id != project.id:
                raise serializers.ValidationError({"parent": "A atividade pai tem de ser do mesmo projeto."})
            # Subir pela árvore: a atividade não pode virar filha de si mesma nem de uma descendente.
            no = parent
            while no is not None and self.instance is not None:
                if no.id == self.instance.id:
                    raise serializers.ValidationError({"parent": "Uma atividade não pode ficar abaixo dela mesma."})
                no = no.parent
        inicio = data.get("start_date") or (self.instance.start_date if self.instance else None)
        fim = data.get("end_date") or (self.instance.end_date if self.instance else None)
        if inicio and fim and fim < inicio:
            raise serializers.ValidationError({"end_date": "A data final não pode ser antes do início."})
        responsible = data.get("responsible")
        if responsible is not None and project is not None and responsible.tenant_id != project.tenant_id:
            raise serializers.ValidationError({"responsible": "Usuário de outra empresa."})
        return data


class ActivityFcaSerializer(serializers.ModelSerializer):
    responsible_name = serializers.SerializerMethodField()
    activity_title = serializers.CharField(source="activity.title", read_only=True)
    alert = serializers.SerializerMethodField()

    class Meta:
        model = ActivityFca
        fields = [
            "id", "activity", "activity_title", "fact", "cause", "action", "due_date",
            "responsible", "responsible_name", "status", "alert", "created_at",
        ]
        read_only_fields = ["created_at"]

    def get_responsible_name(self, obj):
        return _nome(obj.responsible)

    def get_alert(self, obj):
        """atrasado | vence_logo | '' — só para FCA ainda em andamento."""
        from datetime import date, timedelta

        if obj.status != ActivityFca.Status.EM_ANDAMENTO or not obj.due_date:
            return ""
        hoje = date.today()
        if obj.due_date < hoje:
            return "atrasado"
        return "vence_logo" if obj.due_date <= hoje + timedelta(days=7) else ""

    def validate(self, data):
        activity = data.get("activity") or (self.instance.activity if self.instance else None)
        responsible = data.get("responsible")
        if responsible is not None and activity is not None and responsible.tenant_id != activity.project.tenant_id:
            raise serializers.ValidationError({"responsible": "Usuário de outra empresa."})
        return data
