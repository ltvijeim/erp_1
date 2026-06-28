from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from core.exceptions import BusinessRuleViolation

User = get_user_model()

def request_password_reset(email: str) -> None:
    """Generates a secure token and 'sends' the email."""
    user = User.objects.filter(email=email, is_active=True).first()
    if not user:
        # Security best practice: Do not reveal if the email exists
        return 
        
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    
    # In a real system, you would trigger a Celery task here to send the email:
    # send_password_reset_email.delay(user.email, uid, token)
    print(f"DEBUG EMAIL -> User: {user.email} | UID: {uid} | Token: {token}")

def confirm_password_reset(uidb64: str, token: str, new_password: str) -> None:
    """Validates the token and applies the new password."""
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        raise BusinessRuleViolation("Invalid reset link.")

    if not default_token_generator.check_token(user, token):
        raise BusinessRuleViolation("Token is invalid or expired.")

    user.set_password(new_password)
    user.save(update_fields=['password', 'updated_at'])