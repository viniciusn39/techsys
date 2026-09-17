from django.db import migrations


def liberar_kanban(apps, schema_editor):
    """Perfil que já enxerga Projetos passa a enxergar o Kanban (lista vazia = tudo, não mexe)."""
    AccessProfile = apps.get_model("accounts", "AccessProfile")
    for perfil in AccessProfile.objects.all():
        modulos = list(perfil.modules or [])
        if "projetos" in modulos and "kanban" not in modulos:
            modulos.insert(modulos.index("projetos") + 1, "kanban")
            perfil.modules = modulos
            perfil.save(update_fields=["modules"])


class Migration(migrations.Migration):
    dependencies = [("accounts", "0005_usuario_em_varias_empresas")]
    operations = [migrations.RunPython(liberar_kanban, migrations.RunPython.noop)]
