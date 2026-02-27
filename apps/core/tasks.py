"""
Base Task Classes for Organization-Aware Celery Tasks
"""

import logging
from celery import Task
from .context import set_current_organization

logger = logging.getLogger(__name__)


class OrganizationTask(Task):
    """
    Base task class that ensures organization context is properly set.
    """
    
    def __call__(self, *args, **kwargs):
        """
        Wrapper around task execution to ensure organization context.
        """
        from apps.core.models import Organization
        
        organization_id = self.request.headers.get('organization_id')
        
        if not organization_id:
            logger.info(f"Task {self.name} running without organization context")
            return super().__call__(*args, **kwargs)
        
        try:
            org = Organization.objects.get(id=organization_id, is_active=True)
            
            # Set organization context
            set_current_organization(org)
            
            logger.info(f"✓ Task {self.name} running for organization: {org.name}")
            
            # Execute task
            result = super().__call__(*args, **kwargs)
            
            # Cleanup
            set_current_organization(None)
            
            return result
            
        except Organization.DoesNotExist:
            logger.error(f"Task {self.name} failed: Organization {organization_id} not found!")
            raise RuntimeError(f"Organization {organization_id} not found or inactive")
        except Exception as e:
            logger.error(f"Task {self.name} failed: {e}")
            # Ensure cleanup even on error
            try:
                set_current_organization(None)
            except:
                pass
            raise


# PublicSchemaTask is now just a standard task with no special schema handling
class BaseTask(Task):
    """Base task for non-organization specific tasks"""
    def __call__(self, *args, **kwargs):
        return super().__call__(*args, **kwargs)
