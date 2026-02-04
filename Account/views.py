from django.shortcuts import render, redirect
from django.contrib.auth.hashers import check_password, make_password
from django.db import IntegrityError
from Account.models import Account, registerAccount, Role
from Account.decorators import login_prevention, login_required

# Secret admin code // This would normally be in enviroment variables.
ADMIN_ACCESS_CODE = "SKOLA2026" 


@login_prevention
def register(request):
    context = {}

    if request.method == "POST":
        data = request.POST.dict()
        account, errors = registerAccount(data)

        if errors:
            context['errors'] = errors
            context['data'] = data
        else:
            request.session['user_id'] = account.UserID
            request.session['user_name'] = f"{account.FirstName} {account.LastName}"
            return redirect('home')

    return render(request, 'register.html', context)


@login_prevention
def login(request):
    context = {}

    if request.method == "POST":
        email = request.POST.get('email')
        password = request.POST.get('password')
        
        try:
            account = Account.objects.get(Email=email)
            if check_password(password, account.Password):
                request.session['user_id'] = account.UserID
                request.session['user_name'] = f"{account.FirstName} {account.LastName}"
                return redirect('home')
            else:
                context['errors'] = {'general': 'Invalid email or password.'}
        except Account.DoesNotExist:
            context['errors'] = {'general': 'Invalid email or password.'}
        
        context['data'] = {'email': email}

    return render(request, 'login.html', context)


def logout(request):
    request.session.flush()
    return redirect('login')


@login_required
def account_settings(request):
    user_id = request.session.get('user_id')
    
    try:
        account = Account.objects.get(UserID=user_id)
    except Account.DoesNotExist:
        request.session.flush()
        return redirect('login')
    
    context = {
        'account': account,
        'success': request.session.pop('success_message', None),
        'active_tab': request.session.pop('active_tab', None),
        'errors': request.session.pop('delete_errors', None),
    }
    
    return render(request, 'settings.html', context)


@login_required
def update_account(request):
    """Handle account information updates"""
    user_id = request.session.get('user_id')
    context = {}
    
    try:
        account = Account.objects.get(UserID=user_id)
    except Account.DoesNotExist:
        request.session.flush()
        return redirect('login')
    
    if request.method == "POST":
        data = request.POST.dict()
        errors = {}
        
        # Validate first name
        first_name = data.get('first_name', '').strip()
        if not first_name:
            errors['first_name'] = "First name is required."
        
        # Validate last name
        last_name = data.get('last_name', '').strip()
        if not last_name:
            errors['last_name'] = "Last name is required."
        
        # Validate email
        email = data.get('email', '').strip()
        if not email:
            errors['email'] = "Email is required."
        elif '@' not in email:
            errors['email'] = "Enter a valid email address."
        
        # Validate phone
        phone = data.get('phone', '').strip()
        if not phone:
            errors['phone'] = "Phone number is required."
        elif len(phone) > 20:
            errors['phone'] = "Phone number is too long."
        
        # If no validation errors, try to update
        if not errors:
            try:
                account.FirstName = first_name
                account.LastName = last_name
                account.Email = email
                account.Phone = phone
                account.save()
                
                # Update session with new name
                request.session['user_name'] = f"{first_name} {last_name}"
                request.session['success_message'] = "Account updated successfully!"
                
                return redirect('account')
                
            except IntegrityError:
                errors['email'] = "An account with this email already exists."
                context['errors'] = errors
                context['data'] = data
            except Exception as e:
                errors['general'] = "An error occurred while updating your account."
                context['errors'] = errors
                context['data'] = data
        else:
            context['errors'] = errors
            context['data'] = data
    
    if 'account' not in context:
        context['account'] = account
    
    return render(request, 'settings.html', context)


@login_required
def change_password(request):
    """Handle password changes"""
    user_id = request.session.get('user_id')
    context = {}
    
    try:
        account = Account.objects.get(UserID=user_id)
    except Account.DoesNotExist:
        request.session.flush()
        return redirect('login')
    
    if request.method == "POST":
        current_password = request.POST.get('current_password', '')
        new_password = request.POST.get('new_password', '')
        confirm_password = request.POST.get('confirm_password', '')
        
        errors = {}
        
        # Validate current password
        if not current_password:
            errors['current_password'] = "Current password is required."
        elif not check_password(current_password, account.Password):
            errors['current_password'] = "Current password is incorrect."
        
        # Validate new password
        if not new_password:
            errors['new_password'] = "New password is required."
        elif len(new_password) < 6:
            errors['new_password'] = "Password must be at least 6 characters."
        
        # Validate password confirmation
        if not confirm_password:
            errors['confirm_password'] = "Please confirm your new password."
        elif new_password != confirm_password:
            errors['confirm_password'] = "Passwords do not match."
        
        if not errors:
            try:
                account.Password = make_password(new_password)
                account.save()
                request.session['success_message'] = "Password changed successfully!"
                return redirect('account')
            except Exception as e:
                errors['general'] = "An error occurred while changing your password."
                context['errors'] = errors
        else:
            context['errors'] = errors
    
    return render(request, 'settings.html', context)


@login_required
def delete_account(request):
    """Handle account deletion"""
    user_id = request.session.get('user_id')
    context = {}
    errors = {}
    
    try:
        account = Account.objects.get(UserID=user_id)
    except Account.DoesNotExist:
        request.session.flush()
        return redirect('login')
    
    if request.method == "POST":
        # Check for active rentals first (no Return record means still active)
        if account.rentals.filter(return__isnull=True).exists():
            errors['general'] = "You cannot delete your account while you have active rentals. Please return all books first."
            request.session['delete_errors'] = errors
            request.session['active_tab'] = 'delete'
            return redirect('account')

        password = request.POST.get('password', '')
        confirmation = request.POST.get('confirmation', '')
        
        # Verify password
        if not password:
            errors['password'] = "Password is required to delete your account."
        elif not check_password(password, account.Password):
            errors['password'] = "Incorrect password."
        
        # Verify confirmation text
        if confirmation.strip().lower() != 'delete':
            errors['confirmation'] = "Please type 'DELETE' to confirm."
        
        if not errors:
            try:
                account.delete()
                request.session.flush()
                return redirect('register?account_deleted=true')
            except Exception as e:
                errors['general'] = "An error occurred while deleting your account."
        
        # If we still have errors, stash them and redirect back to the delete tab
        if errors:
            request.session['delete_errors'] = errors
            request.session['active_tab'] = 'delete'
            return redirect('account')
    
    return redirect('account')


@login_required
def admin_access(request):
    """Handle secret admin access code submission"""
    user_id = request.session.get('user_id')
    
    try:
        account = Account.objects.get(UserID=user_id)
    except Account.DoesNotExist:
        request.session.flush()
        return redirect('login')
    
    if request.method == "POST":
        admin_code = request.POST.get('admin_code', '')
        
        # Check if code matches
        if admin_code == ADMIN_ACCESS_CODE:
            # Upgrade user to admin (role 2)
            try:
                admin_role = Role.objects.get(RoleID=2)  # Get the Role instance
                account.Role = admin_role
                account.save()
                
                # Set success message
                request.session['success_message'] = "Admin access granted!"
                request.session['active_tab'] = 'profile'
                return redirect('account')
            except Role.DoesNotExist:
                # If Role 2 doesn't exist, silently fail
                return redirect('account')
        else:
            # Incorrect code - silently redirect back without error
            return redirect('account')
    
    # If not POST, redirect to account settings
    return redirect('account')


