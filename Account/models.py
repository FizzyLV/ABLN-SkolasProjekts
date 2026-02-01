from django.db import models, IntegrityError
from django.contrib.auth.hashers import make_password
from django.db.models.signals import post_migrate
from django.dispatch import receiver

class Role(models.Model):
    RoleID = models.AutoField(primary_key=True)
    RoleName = models.CharField(max_length=100)

class Account(models.Model):
    UserID = models.AutoField(primary_key=True)
    Role = models.ForeignKey(Role, on_delete=models.PROTECT, db_column='RoleID', default=1)
    FirstName = models.CharField(max_length=100)
    LastName = models.CharField(max_length=100)
    Password = models.CharField(max_length=256)
    Email = models.EmailField(unique=True)
    Phone = models.CharField(max_length=20, unique=True)
    CreatedAt = models.DateTimeField(auto_now_add=True)

@receiver(post_migrate)
def create_default_roles(sender, **kwargs):
    """Create default roles if they don't exist"""
    if sender.name == 'Account':
        Role.objects.get_or_create(RoleID=1, defaults={'RoleName': 'User'})
        Role.objects.get_or_create(RoleID=2, defaults={'RoleName': 'Admin'})

def checkData(data):
    errors = {}
    required_fields = ['first_name', 'last_name', 'email', 'password', 'phone']
    for field in required_fields:
        if not data.get(field):
            errors[field] = f"{field.replace('_', ' ').title()} is required."
    
    email = data.get('email', '')
    if email and '@' not in email:
        errors['email'] = "Enter a valid email address."
    
    password = data.get('password', '')
    if password and len(password) < 6:
        errors['password'] = "Password must be at least 6 characters."
    
    phone = data.get('phone', '')
    if phone and len(phone) > 20:
        errors['phone'] = "Phone number is too long."
    
    return (len(errors) == 0, errors)

def saveData(data):
    try:
        account = Account.objects.create(
            FirstName=data.get('first_name'),
            LastName=data.get('last_name'),
            Email=data.get('email'),
            Phone=data.get('phone'),
            Password=make_password(data.get('password')),
            Role_id=1  # Use Role_id when setting FK by ID
        )
        return account, None
    except IntegrityError as e:
        if 'email' in str(e).lower():
            return None, "An account with this email already exists."
        elif 'phone' in str(e).lower():
            return None, "An account with this phone number already exists."
        else:
            return None, "An account with these details already exists."
    except Exception as e:
        return None, str(e)

def registerAccount(data):
    valid, errors = checkData(data)
    if not valid:
        return None, errors
    account, save_error = saveData(data)
    if save_error:
        return None, {'general': save_error}
    return account, None