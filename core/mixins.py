from django.http import JsonResponse
from core.utils import build_error_response

class APIAuthMixin:
    """
    Mandatory Mixin for all ERP operational endpoints.
    Ensures the requester is authenticated via Session.
    Returns a strict JSON 401 if unauthenticated.
    """
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse(
                build_error_response("Authentication required. Invalid or missing session.", "UNAUTHORIZED"), 
                status=401
            )
        return super().dispatch(request, *args, **kwargs)