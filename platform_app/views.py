import json
from django.http import JsonResponse, HttpRequest
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

from core.utils import build_error_response
from core.exceptions import HierarchicalIntegrityError

from core.mixins import APIAuthMixin  # <--- INJECTED MIXIN

from platform_app.forms import CreateNodeForm, NodeSettingForm
from platform_app.services import create_node, set_node_setting
from platform_app.selectors import get_node_descendants, resolve_node_setting, check_user_node_authorization

@method_decorator(csrf_exempt, name='dispatch')
class NodeRegistryView(APIAuthMixin, View):  # <--- INHERITS AUTH
    def post(self, request: HttpRequest) -> JsonResponse:
        try:
            payload = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse(build_error_response("Invalid JSON", "BAD_REQUEST"), status=400)
            
        form = CreateNodeForm(payload)
        if not form.is_valid():
            return JsonResponse(build_error_response("Validation Error", "VALIDATION_FAILED", form.errors), status=400)
        
        parent_id = form.cleaned_data.get('parent_node_id')

        # --- AUTHORIZATION ENFORCEMENT ---
        # To create a node, you must have 'GLOBAL_ADMIN' or 'REGION_ADMIN' access to the Parent Node.
        if parent_id:
            has_access = check_user_node_authorization(
                user_id=request.user.id, 
                target_node_id=parent_id, 
                required_role='REGION_ADMIN'
            )
            if not has_access:
                return JsonResponse(
                    build_error_response("You do not have structural authority over this Parent Node.", "FORBIDDEN"), 
                    status=403
                )
        # ---------------------------------

        try:
            node = create_node(
                node_type=form.cleaned_data['node_type'],
                node_name=form.cleaned_data['node_name'],
                parent_node_id=parent_id,
                status=form.cleaned_data.get('status', 'PLANNED')
            )
            return JsonResponse({"node_id": str(node.node_id), "status": "Created"}, status=201)
        except HierarchicalIntegrityError as e:
            return JsonResponse(build_error_response(str(e), "HIERARCHY_VIOLATION"), status=409)

class NodeHierarchyView(APIAuthMixin, View): # <--- INHERITS AUTH
    def get(self, request: HttpRequest, node_id: str) -> JsonResponse:
        
        # --- AUTHORIZATION ENFORCEMENT ---
        # Can only view descendants if you have baseline 'READ_ONLY' access or higher to the root node.
        if not check_user_node_authorization(request.user.id, node_id):
            return JsonResponse(build_error_response("Access Denied to this Node.", "FORBIDDEN"), status=403)
        # ---------------------------------

        descendants = get_node_descendants(node_id)
        data = [{"node_id": str(n.node_id), "name": n.node_name, "type": n.node_type} for n in descendants]
        return JsonResponse({"descendants": data}, status=200)

@method_decorator(csrf_exempt, name='dispatch')
class NodeSettingsView(APIAuthMixin, View): # <--- INHERITS AUTH
    def post(self, request: HttpRequest, node_id: str) -> JsonResponse:
        
        # --- AUTHORIZATION ENFORCEMENT ---
        # Only users with 'IT_ADMIN' role at this node can mutate settings
        if not check_user_node_authorization(request.user.id, node_id, 'IT_ADMIN'):
            return JsonResponse(build_error_response("Node setting mutation requires IT_ADMIN role.", "FORBIDDEN"), status=403)
        # ---------------------------------

        form = NodeSettingForm(json.loads(request.body))
        if not form.is_valid():
            return JsonResponse(build_error_response("Validation Error", "VALIDATION_FAILED", form.errors), status=400)
            
        setting = set_node_setting(
            node_id=node_id,
            setting_key=form.cleaned_data['setting_key'],
            setting_value=form.cleaned_data['setting_value'],
            is_override=form.cleaned_data.get('is_override', False)
        )
        return JsonResponse({"setting_key": setting.setting_key, "status": "Updated"}, status=200)

    def get(self, request: HttpRequest, node_id: str) -> JsonResponse:
        
        # --- AUTHORIZATION ENFORCEMENT ---
        if not check_user_node_authorization(request.user.id, node_id):
            return JsonResponse(build_error_response("Access Denied to this Node.", "FORBIDDEN"), status=403)
        # ---------------------------------

        setting_key = request.GET.get('key')
        if not setting_key:
            return JsonResponse(build_error_response("Query parameter 'key' is required", "BAD_REQUEST"), status=400)
            
        value = resolve_node_setting(node_id, setting_key)
        return JsonResponse({"node_id": node_id, "setting_key": setting_key, "resolved_value": value}, status=200)