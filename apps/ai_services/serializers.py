"""AI Serializers"""
from rest_framework import serializers
from .models import AIModelVersion, AIPrediction


class OrganizationScopedCreateMixin:
    def create(self, validated_data):
        request = self.context.get('request')
        if request and request.user and request.user.is_authenticated and not request.user.is_superuser:
            organization = request.user.get_organization()
            if not organization:
                raise serializers.ValidationError("User is not assigned to an organization.")
            validated_data['organization'] = organization
        return super().create(validated_data)


class AIModelVersionSerializer(OrganizationScopedCreateMixin, serializers.ModelSerializer):
    class Meta:
        model = AIModelVersion
        fields = [
            'id', 'organization', 'name', 'model_type', 'version', 'model_path',
            'is_active', 'accuracy', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class AIPredictionSerializer(OrganizationScopedCreateMixin, serializers.ModelSerializer):
    class Meta:
        model = AIPrediction
        fields = [
            'id', 'organization', 'model_version', 'entity_type', 'entity_id',
            'prediction', 'confidence', 'human_reviewed', 'human_override',
            'reviewed_by', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate(self, attrs):
        request = self.context.get('request')
        model_version = attrs.get('model_version') or getattr(self.instance, 'model_version', None)
        organization = (
            attrs.get('organization')
            or getattr(self.instance, 'organization', None)
            or (request.user.get_organization() if request and request.user and request.user.is_authenticated else None)
        )

        if model_version and organization and model_version.organization_id != organization.id:
            raise serializers.ValidationError("Prediction and model version must belong to the same organization.")

        return attrs


class AIInferenceRequestSerializer(serializers.Serializer):
    model_type = serializers.CharField(max_length=50)
    entity_type = serializers.CharField(max_length=50)
    entity_id = serializers.UUIDField()
    input_data = serializers.JSONField()
    async_mode = serializers.BooleanField(default=False, required=False)
    organization_id = serializers.UUIDField(required=False)

