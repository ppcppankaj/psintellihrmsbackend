"""Authentication app configuration"""
from django.apps import AppConfig


class AuthenticationConfig(AppConfig):
    name = 'apps.authentication'

    def ready(self):
        import apps.authentication.openapi  # noqa: F401
        import apps.authentication.signals  # noqa: F401
