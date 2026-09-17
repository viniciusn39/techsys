"""O que pode receber anexo e como conferir que o registro é da empresa em uso."""

ALVOS = {
    # kind: (app_label.Model, caminho até o tenant)
    "project_activity": ("projects.ProjectActivity", "project__tenant"),
    "kanban_task": ("kanban.Task", "board__tenant"),
}

TAMANHO_MAXIMO = 20 * 1024 * 1024
# Executáveis e scripts não entram; o resto é baixado sempre como anexo, nunca aberto no navegador.
EXTENSOES_BLOQUEADAS = {".exe", ".bat", ".cmd", ".com", ".msi", ".scr", ".ps1", ".vbs", ".js", ".jar", ".sh", ".dll", ".apk"}


def alvo_existe(kind, object_id, tenant):
    from django.apps import apps

    if kind not in ALVOS:
        return False
    modelo, caminho = ALVOS[kind]
    return apps.get_model(modelo).objects.filter(pk=object_id, **{caminho: tenant}).exists()
