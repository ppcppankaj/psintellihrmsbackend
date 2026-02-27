"""Expense Signals"""

from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import ExpenseItem


@receiver(post_save, sender=ExpenseItem)
def update_claim_totals(sender, instance, **kwargs):
    """Update claim totals when an item is saved"""
    instance.claim.update_totals()
