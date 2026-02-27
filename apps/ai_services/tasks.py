"""Celery tasks for AI services."""

from celery import shared_task
from django.apps import apps

from .services import AIPredictionService


@shared_task(bind=True, name="ai_services.run_ai_prediction")
def run_ai_prediction_task(self, organization_id, model_type, entity_type, entity_id, input_data):
    """Execute tenant-safe inference asynchronously."""
    Organization = apps.get_model('core', 'Organization')
    organization = Organization.objects.get(id=organization_id)
    prediction = AIPredictionService.run_prediction(
        organization=organization,
        model_type=model_type,
        entity_type=entity_type,
        entity_id=entity_id,
        input_data=input_data,
    )
    return str(prediction.id)
