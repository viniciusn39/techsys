from django.apps import AppConfig


class ErpConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "erp"
    verbose_name = "Integração ERP"

    def ready(self):
        from . import signals  # noqa: F401
