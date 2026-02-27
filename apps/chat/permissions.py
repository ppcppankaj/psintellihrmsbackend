"""Chat app permissions."""
from rest_framework.permissions import BasePermission


class ChatTenantPermission(BasePermission):
    """Ensures request has organization context for chat operations."""

    message = 'Organization context required for chat.'

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request, 'organization', None)
        )

    def has_object_permission(self, request, view, obj):
        organization = getattr(request, 'organization', None)
        if not organization:
            return False
        obj_org = getattr(obj, 'organization_id', None)
        return obj_org is None or obj_org == organization.id


class IsConversationParticipant(BasePermission):
    """Allow access only to participants of a conversation."""

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.is_superuser:
            return True
        # obj may be Conversation, Message, or ConversationParticipant
        conversation = obj
        if hasattr(obj, 'conversation'):
            conversation = obj.conversation
        if hasattr(conversation, 'participants'):
            return conversation.participants.filter(user=user).exists()
        return False


class CanManageMeetings(BasePermission):
    """HR / admins can manage meetings; others can view their own."""

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        return True  # all authenticated users can access meetings

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.is_superuser:
            return True
        if hasattr(obj, 'created_by_id') and obj.created_by_id == user.id:
            return True
        if hasattr(obj, 'participants'):
            return obj.participants.filter(id=user.id).exists()
        return False
