from django.apps import AppConfig


class BillingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.billing'
    verbose_name = 'Billing & Subscriptions'

    def ready(self):
        # Import signal handlers
        from . import signals  # pylint: disable=unused-import
