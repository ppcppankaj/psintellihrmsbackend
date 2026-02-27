"""Integration Models"""
from django.db import models
from apps.core.models import OrganizationEntity

class Integration(OrganizationEntity):
    """Third-party integrations"""
    name = models.CharField(max_length=100)
    provider = models.CharField(max_length=50)  # slack, teams, zoho, etc.
    config = models.JSONField(default=dict)
    credentials = models.JSONField(default=dict)  # Encrypted
    is_connected = models.BooleanField(default=False)
    last_sync = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        unique_together = ['provider']
    
    def __str__(self):
        return f"{self.name} ({self.provider})"

class Webhook(OrganizationEntity):
    """Outgoing webhooks"""
    name = models.CharField(max_length=100)
    url = models.URLField()
    secret = models.CharField(max_length=255)
    events = models.JSONField(default=list)  # ['employee.created', 'leave.approved']
    headers = models.JSONField(default=dict)
    
    def __str__(self):
        return self.name

class APIKey(OrganizationEntity):
    """API key management"""
    name = models.CharField(max_length=100)
    key = models.CharField(max_length=64, unique=True)
    permissions = models.JSONField(default=list)
    rate_limit = models.PositiveIntegerField(default=1000)
    expires_at = models.DateTimeField(null=True, blank=True)
    last_used = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return self.name
