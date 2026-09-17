from django.db import migrations


def liberar_projetos(apps, schema_editor):
    """Perfil que já enxerga Planos de ação passa a enxergar Projetos (lista vazia = tudo, não mexe)."""
    AccessProfile = apps.get_model("accounts", "AccessProfile")
    for perfil in AccessProfile.objects.all():
        modulos = list(perfil.modules or [])
        if "planos" in modulos and "projetos" not in modulos:
            modulos.insert(modulos.index("planos") + 1, "projetos")
            perfil.modules = modulos
            perfil.save(update_fields=["modules"])


class Migration(migrations.Migration):
    dependencies = [("accounts", "0002_perfis_de_acesso")]
    operations = [migrations.RunPython(liberar_projetos, migrations.RunPython.noop)]
