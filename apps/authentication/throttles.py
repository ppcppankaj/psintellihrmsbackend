from rest_framework.throttling import SimpleRateThrottle


class LoginRateThrottle(SimpleRateThrottle):
    scope = "login"

    def get_cache_key(self, request, view):
        ident = self.get_ident(request)
        return f"login:{ident}"


class PasswordResetRateThrottle(SimpleRateThrottle):
    scope = "password_reset"

    def get_cache_key(self, request, view):
        ident = self.get_ident(request)
        return f"password_reset:{ident}"


class TwoFactorRateThrottle(SimpleRateThrottle):
    scope = "two_factor"

    def get_cache_key(self, request, view):
        ident = self.get_ident(request)
        return f"2fa:{ident}"
