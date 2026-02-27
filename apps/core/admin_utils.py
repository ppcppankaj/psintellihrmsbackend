from django.contrib.admin.utils import get_deleted_objects as django_get_deleted_objects
from django.db import utils
from django.conf import settings

class SafeDeleteMixin:
    """
    🏢 Refactored Mixin for ModelAdmin.
    Schema-based isolation checks removed. Standard Django deletion logic used.
    """
    def get_deleted_objects(self, objs, request):
        return django_get_deleted_objects(objs, request, self.admin_site)

    def delete_model(self, request, obj):
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        queryset.delete()
