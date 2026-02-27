"""
Performance Signals - Automated Training Recommendations
"""

from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import EmployeeCompetency, TrainingRecommendation

@receiver(post_save, sender=EmployeeCompetency)
def create_training_recommendation(sender, instance, created, **kwargs):
    """
    Automatically suggest training if a competency gap exists.
    """
    if instance.gap and instance.gap > 0:
        # Check if recommendation already exists for this competency/cycle/employee
        exists = TrainingRecommendation.objects.filter(
            employee=instance.employee,
            competency=instance.competency,
            cycle=instance.cycle
        ).exists()
        
        if not exists:
            TrainingRecommendation.objects.create(
                employee=instance.employee,
                competency=instance.competency,
                cycle=instance.cycle,
                suggested_training=f"Advanced Training for {instance.competency.name}",
                priority='high' if instance.gap >= 2 else 'medium',
                notes=f"Auto-generated due to competency gap of {instance.gap}.",
                organization=instance.organization
            )
