from django.conf import settings


class ApplicationSecurityHeadersMiddleware:
    """Apply a restrictive browser policy to every application response."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(self), microphone=(), geolocation=(), payment=(self)",
        )
        response.headers.setdefault(
            "Content-Security-Policy",
            "; ".join(
                (
                    "default-src 'self'",
                    "base-uri 'self'",
                    "object-src 'none'",
                    "frame-ancestors 'none'",
                    "form-action 'self'",
                    "script-src 'self' 'unsafe-inline'",
                    "style-src 'self' 'unsafe-inline'",
                    "img-src 'self' data: blob:",
                    "font-src 'self' data:",
                    "connect-src 'self'",
                    "manifest-src 'self'",
                    "worker-src 'self' blob:",
                    "media-src 'self' blob:",
                    "frame-src https://yookassa.ru https://*.yookassa.ru",
                    *((("upgrade-insecure-requests",) if not settings.LOCAL_DEV else ())),
                )
            ),
        )
        return response
