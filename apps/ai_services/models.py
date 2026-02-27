"""AI Models"""
from django.db import models
from django.core.exceptions import ValidationError
from apps.core.models import OrganizationEntity


class AIModelVersion(OrganizationEntity):
    """AI model versioning"""
    name = models.CharField(max_length=100)
    model_type = models.CharField(max_length=50)  # resume_parser, attrition, burnout, etc.
    version = models.CharField(max_length=20)
    model_path = models.CharField(max_length=500)
    accuracy = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.name} v{self.version}"

    def save(self, *args, **kwargs):
        if not self.organization_id and self.created_by_id:
            self.organization = self.created_by.get_organization()
        super().save(*args, **kwargs)


class AIPrediction(OrganizationEntity):
    """AI prediction log"""
    model_version = models.ForeignKey(AIModelVersion, on_delete=models.SET_NULL, null=True)
    entity_type = models.CharField(max_length=50)
    entity_id = models.UUIDField()
    
    prediction = models.JSONField()
    confidence = models.DecimalField(max_digits=5, decimal_places=2)
    
    human_reviewed = models.BooleanField(default=False)
    human_override = models.JSONField(null=True, blank=True)
    reviewed_by = models.ForeignKey('employees.Employee', on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['organization', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.entity_type}:{self.entity_id} - {self.confidence}%"

    def clean(self):
        if self.model_version_id and self.organization_id:
            if self.model_version.organization_id != self.organization_id:
                raise ValidationError("Prediction organization must match model version organization.")

        if self.reviewed_by_id and self.organization_id:
            if self.reviewed_by.organization_id != self.organization_id:
                raise ValidationError("Reviewer must belong to the same organization as the prediction.")

    def save(self, *args, **kwargs):
        if not self.organization_id and self.model_version_id:
            self.organization = self.model_version.organization
        if not self.organization_id and self.reviewed_by_id:
            self.organization = self.reviewed_by.organization
        if not self.organization_id and self.created_by_id:
            self.organization = self.created_by.get_organization()
        self.clean()
        super().save(*args, **kwargs)
