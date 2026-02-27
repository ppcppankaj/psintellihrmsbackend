"""Integrations Admin"""
from django.contrib import admin
from .models import Integration, Webhook, APIKey

@admin.register(Integration)
class IntegrationAdmin(admin.ModelAdmin):
    list_display = ['name', 'provider', 'is_connected', 'last_sync', 'is_active']
    list_filter = ['provider', 'is_connected', 'is_active']
    search_fields = ['name', 'provider']

@admin.register(Webhook)
class WebhookAdmin(admin.ModelAdmin):
    list_display = ['name', 'url', 'is_active']
    list_filter = ['is_active']

@admin.register(APIKey)
class APIKeyAdmin(admin.ModelAdmin):
    list_display = ['name', 'rate_limit', 'expires_at', 'last_used', 'is_active']
    list_filter = ['is_active']
    search_fields = ['name']
