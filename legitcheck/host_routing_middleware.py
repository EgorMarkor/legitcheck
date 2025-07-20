class DomainRoutingMiddleware:
    """Switch URL configuration based on the request host."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.get_host().split(':')[0].lower()
        if host in ("checkerlegit.com", "www.checkerlegit.com"):
            request.urlconf = "legitcheck.urls_pcwebapp"
        else:
            request.urlconf = "legitcheck.urls_webapp"
        return self.get_response(request)
