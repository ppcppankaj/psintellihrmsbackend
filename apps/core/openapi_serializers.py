from rest_framework import serializers

class EmptySerializer(serializers.Serializer):
    """
    Used for APIViews that do not accept or return structured bodies.
    Required for drf-spectacular schema generation.
    """
    pass
