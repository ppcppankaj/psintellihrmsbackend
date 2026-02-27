"""Performance app configuration"""
from django.apps import AppConfig


class PerformanceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.performance'
    verbose_name = 'Performance Management'

    def ready(self):
        import apps.performance.signals
