"""
Integration Services - Webhooks and API management
"""

import requests
import hmac
import hashlib
import json
from .models import Webhook, Integration

class IntegrationService:
    """
    Logic for triggering outgoing webhooks and syncing with external providers.
    """

    @staticmethod
    def trigger_webhook(event_name, payload, organization):
        """
        Dispatch an outgoing webhook for a specific event.
        """
        webhooks = Webhook.objects.filter(
            organization=organization,
            is_active=True,
            events__contains=[event_name]
        )
        
        results = []
        for webhook in webhooks:
            # Generate signature
            signature = hmac.new(
                webhook.secret.encode(),
                json.dumps(payload).encode(),
                hashlib.sha256
            ).hexdigest()
            
            headers = webhook.headers or {}
            headers['X-HRMS-Event'] = event_name
            headers['X-HRMS-Signature'] = signature
            
            try:
                # In production, this would be an async task (Celery)
                # response = requests.post(webhook.url, json=payload, headers=headers, timeout=5)
                # results.append({'webhook': webhook.name, 'status': response.status_code})
                results.append({'webhook': webhook.name, 'status': 'skipped_in_dev'})
            except Exception as e:
                results.append({'webhook': webhook.name, 'error': str(e)})
                
        return results

    @staticmethod
    def sync_slack(organization, message):
        """
        Example: Push a notification to Slack.
        """
        integration = Integration.objects.filter(organization=organization, provider='slack', is_connected=True).first()
        if integration:
            # logic to post to Slack webhook/API
            pass
        return True
