import uuid
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager

class TimeStampedModel(models.Model):
    """
    Abstract base class providing self-updating 'created_at' and 'updated_at' fields.
    Maps directly to PostgreSQL TIMESTAMPTZ.
    Assumes Django settings.USE_TZ = True.
    """
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

class ERPBaseModel(TimeStampedModel):
    """
    Abstract base class combining UUID primary keys with timestamp audits.
    Child models will inherit this class and shadow the 'id' field with their 
    specific explicit name if required (e.g., 'node_id', 'item_id').
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True

class ERPUserManager(BaseUserManager):
    """Custom manager enforcing UUIDs and strict creation rules."""
    
    def create_user(self, username, email, password=None, **extra_fields):
        if not username:
            raise ValueError('The Username field must be set')
        if not email:
            raise ValueError('The Email field must be set')
        
        email = self.normalize_email(email)
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(username, email, password, **extra_fields)


class ERPUser(AbstractBaseUser, PermissionsMixin, TimeStampedModel):
    """
    The Master System Identity.
    Strictly isolated from HR/HCM data. Handles Authentication only.
    Authorization is handled via platform_app.NodeAccessAssignment.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = models.CharField(max_length=150, unique=True)
    email = models.EmailField(unique=True)
    
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    objects = ERPUserManager()

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email']

    class Meta:
        db_table = 'core_users'

    def __str__(self):
        return self.username