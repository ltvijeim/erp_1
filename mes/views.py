import json
from django.http import JsonResponse, HttpRequest
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

from core.utils import build_error_response
from core.mixins import APIAuthMixin
from core.exceptions import BusinessRuleViolation
from mes.forms import CreateWorkOrderForm, MaterialIssueForm, OperationYieldForm
from mes.services import create_and_release_work_order, log_material_issue, log_yield, complete_work_order

@method_decorator(csrf_exempt, name='dispatch')
class WorkOrderAPIView(APIAuthMixin, View):
    def post(self, request: HttpRequest) -> JsonResponse:
        try:
            payload = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse(build_error_response("Invalid JSON", "BAD_REQUEST"), status=400)

        form = CreateWorkOrderForm(payload)
        if not form.is_valid():
            return JsonResponse(build_error_response("Validation Error", "VALIDATION_FAILED", form.errors), status=400)

        try:
            wo = create_and_release_work_order(
                item_id=form.cleaned_data['item_id'],
                node_id=form.cleaned_data['node_id'],
                target_qty=form.cleaned_data['target_quantity']
            )
            return JsonResponse({"wo_id": str(wo.wo_id), "status": "RELEASED"}, status=201)
        except BusinessRuleViolation as e:
            return JsonResponse(build_error_response(str(e), "BUSINESS_RULE_VIOLATION"), status=409)

@method_decorator(csrf_exempt, name='dispatch')
class MaterialIssueAPIView(APIAuthMixin, View):
    """Highly concurrent endpoint for RF Scanners."""
    def post(self, request: HttpRequest, wo_id: str) -> JsonResponse:
        try:
            payload = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse(build_error_response("Invalid JSON", "BAD_REQUEST"), status=400)

        form = MaterialIssueForm(payload)
        if not form.is_valid():
            return JsonResponse(build_error_response("Validation Error", "VALIDATION_FAILED", form.errors), status=400)

        try:
            pt = log_material_issue(
                wo_id=wo_id,
                component_item_id=form.cleaned_data['component_item_id'],
                work_center_id=form.cleaned_data['work_center_id'],
                scanned_qty=form.cleaned_data['scanned_qty'],
                batch_ref=form.cleaned_data['batch_serial_ref'],
                operator_id=request.user.id
            )
            # Returns 201 immediately; Cost rollup happens in the background via Celery.
            return JsonResponse({"transaction_id": str(pt.transaction_id), "status": "Logged"}, status=201)
        except BusinessRuleViolation as e:
            return JsonResponse(build_error_response(str(e), "BUSINESS_RULE_VIOLATION"), status=409)

@method_decorator(csrf_exempt, name='dispatch')
class WorkOrderCompletionView(APIAuthMixin, View):
    def post(self, request: HttpRequest, wo_id: str) -> JsonResponse:
        try:
            wo = complete_work_order(wo_id)
            return JsonResponse({"wo_id": str(wo.wo_id), "status": "COMPLETED"}, status=200)
        except BusinessRuleViolation as e:
            return JsonResponse(build_error_response(str(e), "ALLOCATION_HARD_STOP"), status=409)