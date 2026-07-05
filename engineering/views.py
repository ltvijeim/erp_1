import json
from django.http import JsonResponse, HttpRequest
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from core.utils import build_error_response
from core.mixins import APIAuthMixin
from core.exceptions import BusinessRuleViolation, HierarchicalIntegrityError, ImmutableStateViolation
from engineering.forms import DraftBOMForm, BOMLineForm, ECOApprovalForm
from engineering.services import create_draft_bom, add_bom_line, approve_eco
from engineering.tasks import execute_eco_transition

@method_decorator(csrf_exempt, name='dispatch')
class BOMRegistryView(APIAuthMixin, View):
    def post(self, request: HttpRequest) -> JsonResponse:
        try:
            payload = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse(build_error_response("Invalid JSON", "BAD_REQUEST"), status=400)
            
        form = DraftBOMForm(payload)
        if not form.is_valid():
            return JsonResponse(build_error_response("Validation Error", "VALIDATION_FAILED", form.errors), status=400)
            
        try:
            bom = create_draft_bom(
                item_id=form.cleaned_data['item_id'],
                node_id=form.cleaned_data['node_id'],
                bom_type=form.cleaned_data['bom_type'],
                revision_level=form.cleaned_data['revision_level']
            )
            return JsonResponse({"bom_id": str(bom.bom_id), "status": "DRAFT Created"}, status=201)
        except BusinessRuleViolation as e:
            return JsonResponse(build_error_response(str(e), "BUSINESS_RULE_VIOLATION"), status=409)

@method_decorator(csrf_exempt, name='dispatch')
class BOMLineView(APIAuthMixin, View):
    def post(self, request: HttpRequest, bom_id: str) -> JsonResponse:
        try:
            payload = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse(build_error_response("Invalid JSON", "BAD_REQUEST"), status=400)
            
        form = BOMLineForm(payload)
        if not form.is_valid():
            return JsonResponse(build_error_response("Validation Error", "VALIDATION_FAILED", form.errors), status=400)
            
        try:
            line = add_bom_line(
                bom_id=bom_id,
                component_item_id=form.cleaned_data['component_item_id'],
                quantity=form.cleaned_data['quantity'],
                scrap_factor=form.cleaned_data.get('scrap_factor', 0.0),
                valid_from=form.cleaned_data.get('valid_from'),
                valid_to=form.cleaned_data.get('valid_to')
            )
            return JsonResponse({"bom_line_id": str(line.bom_line_id), "status": "Added"}, status=201)
        except (BusinessRuleViolation, HierarchicalIntegrityError, ImmutableStateViolation) as e:
            return JsonResponse(build_error_response(str(e), "INTEGRITY_VIOLATION"), status=409)

@method_decorator(csrf_exempt, name='dispatch')
class ECOExecutionView(APIAuthMixin, View):
    def post(self, request: HttpRequest, eco_id: str) -> JsonResponse:
        # Offload strict effectivity handoffs to Celery
        execute_eco_transition.delay(eco_id)
        return JsonResponse({"status": "ECO Execution Queued", "eco_id": eco_id}, status=202)