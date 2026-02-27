"""Integration Serializers"""
from rest_framework import serializers
from .models import Integration, Webhook, APIKey


class IntegrationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Integration
        fields = [
            'id', 'organization', 'name', 'provider', 'config', 'credentials',
            'is_connected', 'last_sync', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at']
        extra_kwargs = {'credentials': {'write_only': True}}


class WebhookSerializer(serializers.ModelSerializer):
    class Meta:
        model = Webhook
        fields = [
            'id', 'organization', 'name', 'url', 'secret', 'events', 'headers',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at']
        extra_kwargs = {'secret': {'write_only': True}}


class APIKeySerializer(serializers.ModelSerializer):
    class Meta:
        model = APIKey
        fields = [
            'id', 'organization', 'name', 'key', 'permissions', 'rate_limit',
            'expires_at', 'last_used', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'organization', 'key', 'last_used', 'created_at', 'updated_at']
