from Account.models import Account

def user_context(request):
    """Add user info to all templates"""
    context = {
        'is_admin': False,
    }
    
    user_id = request.session.get('user_id')
    if user_id:
        try:
            account = Account.objects.get(UserID=user_id)
            context['is_admin'] = account.Role.RoleID == 2 if account.Role else False
        except Account.DoesNotExist:
            pass
    
    return context
