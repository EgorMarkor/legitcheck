class WebappAuthMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tg_id = request.session.get('webapp_user_tgId')
        request.webapp_user = None
        if tg_id is not None:
            from webapp.models import User
            try:
                request.webapp_user = User.objects.get(tgId=tg_id)
            except User.DoesNotExist:
                pass
        return self.get_response(request)
