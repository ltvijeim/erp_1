import json
from django.http import JsonResponse, HttpRequest
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

from core.utils import build_error_response
from core.exceptions import BusinessRuleViolation
from core.mixins import APIAuthMixin

from mdm.forms import CreateItemForm, ExtendItemForm, BPRoleForm
from mdm.services import create_global_item, extend_item_to_node, assign_bp_role_to_node
from mdm.selectors import get_global_item, is_item_active_at_node

@method_decorator(csrf_exempt, name='dispatch')
class ItemRegistryView(APIAuthMixin, View):
    def post(self, request: HttpRequest) -> JsonResponse:
        try:
            payload = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse(build_error_response("Invalid JSON payload", "BAD_REQUEST"), status=400)
            
        form = CreateItemForm(payload)
        if not form.is_valid():
            return JsonResponse(build_error_response("Validation Error", "VALIDATION_FAILED", form.errors), status=400)
            
        try:
            item = create_global_item(
                sku=form.cleaned_data['sku'],
                item_class=form.cleaned_data['item_class'],
                base_uom=form.cleaned_data['base_uom'],
                description=form.cleaned_data['global_description'],
                traceability=form.cleaned_data.get('traceability_type', 'NONE')
            )
            return JsonResponse({"item_id": str(item.item_id), "sku": item.sku, "status": "Registered"}, status=201)
        except BusinessRuleViolation as e:
            return JsonResponse(build_error_response(str(e), "BUSINESS_RULE_VIOLATION"), status=409)

    def get(self, request: HttpRequest, item_id: str) -> JsonResponse:
        item = get_global_item(item_id)
        if not item:
            return JsonResponse(build_error_response("Item not found.", "NOT_FOUND"), status=404)
        return JsonResponse({
            "item_id": str(item.item_id),
            "sku": item.sku,
            "item_class": item.item_class,
            "base_uom": item.base_uom,
            "traceability": item.traceability_type,
            "global_status": item.global_status
        }, status=200)

@method_decorator(csrf_exempt, name='dispatch')
class ItemNodeExtensionView(APIAuthMixin, View):
    def post(self, request: HttpRequest, item_id: str) -> JsonResponse:
        try:
            payload = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse(build_error_response("Invalid JSON payload", "BAD_REQUEST"), status=400)
            
        form = ExtendItemForm(payload)
        if not form.is_valid():
            return JsonResponse(build_error_response("Validation Error", "VALIDATION_FAILED", form.errors), status=400)
            
        try:
            extension = extend_item_to_node(
                item_id=item_id,
                node_id=form.cleaned_data['node_id'],
                costing_method=form.cleaned_data['costing_method'],
                replenishment_rule=form.cleaned_data['replenishment_rule']
            )
            return JsonResponse({"extension_id": str(extension.extension_id), "status": "Extended"}, status=201)
        except BusinessRuleViolation as e:
            return JsonResponse(build_error_response(str(e), "BUSINESS_RULE_VIOLATION"), status=409)

    def get(self, request: HttpRequest, item_id: str, node_id: str) -> JsonResponse:
        active = is_item_active_at_node(item_id, node_id)
        return JsonResponse({"item_id": item_id, "node_id": node_id, "is_active_for_transactions": active}, status=200)

@method_decorator(csrf_exempt, name='dispatch')
class BusinessPartnerRoleView(APIAuthMixin, View):
    def post(self, request: HttpRequest) -> JsonResponse:
        try:
            payload = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse(build_error_response("Invalid JSON payload", "BAD_REQUEST"), status=400)
            
        form = BPRoleForm(payload)
        if not form.is_valid():
            return JsonResponse(build_error_response("Validation Error", "VALIDATION_FAILED", form.errors), status=400)
            
        try:
            role_assignment = assign_bp_role_to_node(
                bp_id=form.cleaned_data['bp_id'],
                node_id=form.cleaned_data['node_id'],
                role=form.cleaned_data['bp_role'],
                financial_terms=form.cleaned_data['financial_terms']
            )
            return JsonResponse({"role_id": str(role_assignment.role_id), "status": "Assigned"}, status=201)
        except BusinessRuleViolation as e:
            return JsonResponse(build_error_response(str(e), "BUSINESS_RULE_VIOLATION"), status=409)