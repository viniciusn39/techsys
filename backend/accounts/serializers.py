from rest_framework import serializers

from .models import OrgUnit, Tenant, User


class TenantSerializer(serializers.ModelSerializer):
    admin_email = serializers.EmailField(write_only=True, required=False)
    admin_password = serializers.CharField(write_only=True, required=False)
    admin_name = serializers.CharField(write_only=True, required=False)
    users_count = serializers.IntegerField(source="users.count", read_only=True)

    class Meta:
        model = Tenant
        fields = [
            "id", "name", "slug", "cnpj", "is_active", "created_at",
            "users_count", "admin_email", "admin_password", "admin_name",
        ]

    def create(self, validated_data):
        from strategy.provisioning import bootstrap_tenant

        admin_email = validated_data.pop("admin_email", None)
        admin_password = validated_data.pop("admin_password", None)
        admin_name = validated_data.pop("admin_name", "")
        tenant = super().create(validated_data)

        # Empresa nova já nasce utilizável: unidade raiz, mapa ativo do ano e
        # as perspectivas padrão (que o admin pode editar depois).
        provisioned = bootstrap_tenant(tenant)

        if admin_email and admin_password:
            User.objects.create_user(
                email=admin_email,
                password=admin_password,
                first_name=admin_name or "Administrador",
                tenant=tenant,
                role=User.Role.ADMIN,
                org_unit=provisioned["org_unit"],
            )
        return tenant


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)
    org_unit_name = serializers.CharField(source="org_unit.name", read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "email", "first_name", "last_name", "role", "cargo",
            "org_unit", "org_unit_name", "is_active", "password",
        ]

    def validate_org_unit(self, value):
        if value is not None:
            tenant = self.context.get("tenant")
            if tenant and value.tenant_id != tenant.id:
                raise serializers.ValidationError("Unidade de outra empresa.")
        return value

    def validate_role(self, value):
        if value == User.Role.ROOT:
            raise serializers.ValidationError("Papel root não pode ser atribuído por aqui.")
        return value

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        user = User(**validated_data)
        user.set_password(password or User.objects.make_random_password())
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        user = super().update(instance, validated_data)
        if password:
            user.set_password(password)
            user.save()
        return user


class OrgUnitSerializer(serializers.ModelSerializer):
    manager_name = serializers.CharField(source="manager.first_name", read_only=True)

    class Meta:
        model = OrgUnit
        fields = ["id", "parent", "name", "kind", "manager", "manager_name", "order"]

    def validate_parent(self, value):
        if value is not None:
            tenant = self.context.get("tenant")
            if tenant and value.tenant_id != tenant.id:
                raise serializers.ValidationError("Unidade pai de outra empresa.")
        return value


class MeSerializer(serializers.ModelSerializer):
    tenant = TenantSerializer(read_only=True)

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "role", "cargo", "org_unit", "tenant"]
