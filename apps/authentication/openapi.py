from drf_spectacular.extensions import OpenApiAuthenticationExtension

class OrganizationAwareJWTAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = 'apps.authentication.authentication.OrganizationAwareJWTAuthentication'
    name = 'JWTAuth'

    def get_security_definition(self, auto_schema):
        return {
            'type': 'http',
            'scheme': 'bearer',
            'bearerFormat': 'JWT',
        }
