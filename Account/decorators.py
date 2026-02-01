from django.shortcuts import redirect
from functools import wraps
from Account.models import Account

def login_required(view_func):
    """
    Decorator that checks if a user is logged in via session.
    Redirects to login page if not authenticated.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if 'user_id' not in request.session:
            return redirect('login')
        return view_func(request, *args, **kwargs)
    return wrapper

def login_prevention(view_func):
    """
    Decorator that prevents logged-in users from accessing login/register pages.
    Redirects to home page if already authenticated.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if 'user_id' in request.session:  # Changed: if user IS logged in
            return redirect('home')
        return view_func(request, *args, **kwargs)
    return wrapper

def admin_required(view_func):
    """
    Decorator that checks if a user is an admin (RoleID = 2).
    Redirects to home page if not logged in or not an admin.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user_id = request.session.get('user_id')
        
        # Check if user is logged in
        if not user_id:
            return redirect('login')
        
        # Check if user is admin (RoleID = 2)
        try:
            account = Account.objects.get(UserID=user_id)
            if account.Role.RoleID != 2:
                return redirect('home')
        except Account.DoesNotExist:
            return redirect('login')
        
        return view_func(request, *args, **kwargs)
    return wrapper