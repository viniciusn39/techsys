from django.db import migrations
from django.db.models import F


def fatores_a_partir_do_impacto(apps, schema_editor):
    """Item antigo só tinha impacto (1–5): os três fatores nascem iguais a ele, e a ordem entre os itens se mantém."""
    SwotItem = apps.get_model("strategy", "SwotItem")
    SwotItem.objects.update(importance=F("impact"), intensity=F("impact"), trend=F("impact"))


class Migration(migrations.Migration):
    dependencies = [("strategy", "0008_swot_pontuacao")]
    operations = [migrations.RunPython(fatores_a_partir_do_impacto, migrations.RunPython.noop)]
