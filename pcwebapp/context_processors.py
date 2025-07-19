from webapp.models import User

def webapp_user(request):
    tg_id = request.session.get('webapp_user_tgId')
    user = None
    if tg_id:
        try:
            user = User.objects.get(tgId=tg_id)
        except User.DoesNotExist:
            pass
    return {'webapp_user': user}
