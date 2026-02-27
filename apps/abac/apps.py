"""ABAC app configuration"""
from django.apps import AppConfig


class AbacConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.abac'
    verbose_name = 'Attribute-Based Access Control'
    
    def ready(self):
        """Import signals when app is ready"""
        try:
            from . import signals  # noqa
        except ImportError:
            pass
