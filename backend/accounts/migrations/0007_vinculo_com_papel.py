from django.db import migrations, models
import django.db.models.deletion


def copiar_vinculos(apps, schema_editor):
    """Vínculos criados antes do papel por empresa mantêm o papel que a pessoa já exercia (o do cadastro)."""
    User = apps.get_model("accounts", "User")
    Membership = apps.get_model("accounts", "Membership")
    Antigo = User.extra_tenants.through
    for v in Antigo.objects.all().select_related("user"):
        papel = v.user.role if v.user.role in ("admin", "gestor", "colaborador") else "colaborador"
        Membership.objects.get_or_create(user_id=v.user_id, tenant_id=v.tenant_id, defaults={"role": papel})


class Migration(migrations.Migration):
    dependencies = [("accounts", "0006_modulo_kanban")]
    operations = [
        migrations.CreateModel(
            name="Membership",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role", models.CharField(choices=[("admin", "Administrador"), ("gestor", "Gestor"), ("colaborador", "Colaborador")], default="colaborador", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="memberships", to="accounts.tenant")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="memberships", to="accounts.user")),
            ],
        ),
        migrations.AddConstraint(
            model_name="membership",
            constraint=models.UniqueConstraint(fields=("user", "tenant"), name="uniq_membership"),
        ),
        migrations.RunPython(copiar_vinculos, migrations.RunPython.noop),
        migrations.RemoveField(model_name="user", name="extra_tenants"),
        migrations.AddField(
            model_name="user",
            name="extra_tenants",
            field=models.ManyToManyField(blank=True, related_name="guest_users", through="accounts.Membership", to="accounts.tenant", verbose_name="outras empresas"),
        ),
    ]
