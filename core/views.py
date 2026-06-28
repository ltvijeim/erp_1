import json
from django.http import JsonResponse, HttpRequest
from django.views import View
from django.contrib.auth import authenticate, login, logout
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

from core.forms import APILoginForm, PasswordResetRequestForm, PasswordResetConfirmForm
from core.services import request_password_reset, confirm_password_reset
from core.utils import build_error_response
from core.exceptions import BusinessRuleViolation

@method_decorator(csrf_exempt, name='dispatch')
class APILoginView(View):
    def post(self, request: HttpRequest) -> JsonResponse:
        try:
            payload = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse(build_error_response("Invalid JSON", "BAD_REQUEST"), status=400)
            
        form = APILoginForm(payload)
        if not form.is_valid():
            return JsonResponse(build_error_response("Validation Error", "VALIDATION_FAILED", form.errors), status=400)

        user = authenticate(
            request, 
            username=form.cleaned_data['username'], 
            password=form.cleaned_data['password']
        )

        if user is not None:
            login(request, user)
            return JsonResponse({"status": "Login successful", "user_id": str(user.id)}, status=200)
        else:
            return JsonResponse(build_error_response("Invalid credentials", "UNAUTHORIZED"), status=401)

class APILogoutView(View):
    def post(self, request: HttpRequest) -> JsonResponse:
        logout(request)
        return JsonResponse({"status": "Logout successful"}, status=200)

@method_decorator(csrf_exempt, name='dispatch')
class PasswordResetRequestAPIView(View):
    def post(self, request: HttpRequest) -> JsonResponse:
        form = PasswordResetRequestForm(json.loads(request.body))
        if form.is_valid():
            request_password_reset(form.cleaned_data['email'])
        # Always return 200 OK to prevent email enumeration attacks
        return JsonResponse({"status": "If the email exists, a reset link has been sent."}, status=200)

@method_decorator(csrf_exempt, name='dispatch')
class PasswordResetConfirmAPIView(View):
    def post(self, request: HttpRequest) -> JsonResponse:
        form = PasswordResetConfirmForm(json.loads(request.body))
        if not form.is_valid():
            return JsonResponse(build_error_response("Validation Error", "VALIDATION_FAILED", form.errors), status=400)
            
        try:
            confirm_password_reset(
                uidb64=form.cleaned_data['uidb64'],
                token=form.cleaned_data['token'],
                new_password=form.cleaned_data['new_password']
            )
            return JsonResponse({"status": "Password successfully reset."}, status=200)
        except BusinessRuleViolation as e:
            return JsonResponse(build_error_response(str(e), "RESET_FAILED"), status=400)