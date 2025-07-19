from functools import wraps
from django.shortcuts import redirect
from webapp.models import User as WebUser

def webapp_login_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        tg_id = request.session.get('webapp_user_tgId')
        if not tg_id:
            return redirect('pc_home')  # редирект на страницу логина, если не в сессии

        try:
            request.webapp_user = WebUser.objects.get(tgId=tg_id)
        except WebUser.DoesNotExist:
            return redirect('pc_home')

        return view_func(request, *args, **kwargs)
    return _wrapped


def webapp_user_optional(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        tg_id = request.session.get('webapp_user_tgId')
        request.webapp_user = None
        if tg_id:
            request.webapp_user = WebUser.objects.filter(tgId=tg_id).first()
        return view_func(request, *args, **kwargs)
    return _wrapped
