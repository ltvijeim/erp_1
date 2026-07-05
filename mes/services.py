from uuid import UUID
from decimal import Decimal
from django.db import transaction, IntegrityError
from mes.models import WorkOrder, WOMaterialRequirement, WOOperation, ProductionTransaction, WorkCenter
from engineering.selectors import get_active_bom_for_node, get_bom_explosion, get_routing_sequence
from core.exceptions import BusinessRuleViolation, ResourceLockedException
from django.utils import timezone
from mes.tasks import execute_cost_rollup

@transaction.atomic
def create_and_release_work_order(item_id: UUID, node_id: UUID, target_qty: Decimal) -> WorkOrder:
    """
    The Snapshot Principle.
    Instantiates WO, copies BOM to WOMaterialRequirement, Routings to WOOperation.
    Transitions to 'RELEASED'.
    """
    # 1. Fetch active recipe from Engineering via selector (Logical Inheritance applied)
    active_bom = get_active_bom_for_node(item_id, node_id)
    if not active_bom:
        raise BusinessRuleViolation("No ACTIVE BOM found for this Item at this Node.")

    # 2. Create the WO
    wo = WorkOrder.objects.create(
        node_id=node_id,
        item_id=item_id,
        target_quantity=target_qty,
        status=WorkOrder.WOStatus.RELEASED
    )

    # 3. Snapshot the Material Requirements
    ingredients = get_bom_explosion(active_bom.bom_id, timezone.now().date())
    requirements = [
        WOMaterialRequirement(
            wo=wo,
            component_item_id=line.component_item_id,
            required_qty=line.quantity * target_qty
        ) for line in ingredients
    ]
    WOMaterialRequirement.objects.bulk_create(requirements)

    # 4. Snapshot the Routings
    routings = get_routing_sequence(active_bom.bom_id)
    operations = [
        WOOperation(
            wo=wo,
            operation_seq=rtg.operation_seq,
            work_center_id=rtg.work_center_id
        ) for rtg in routings
    ]
    WOOperation.objects.bulk_create(operations)

    return wo

@transaction.atomic
def log_material_issue(wo_id: UUID, component_item_id: UUID, work_center_id: UUID, scanned_qty: Decimal, batch_ref: str, operator_id: UUID) -> ProductionTransaction:
    """
    Mandatory Concurrency Pattern.
    Safely increments consumption under heavy load from multiple PLCs/Scanners.
    """
    try:
        # 1. Thread-safe row lock. Blocks other scanner threads until transaction completes.
        req = WOMaterialRequirement.objects.select_for_update(nowait=False).get(
            wo_id=wo_id, component_item_id=component_item_id
        )
    except WOMaterialRequirement.DoesNotExist:
        raise BusinessRuleViolation("Component is not required for this Work Order.")

    # 2. Increment safely in memory (safe because of the lock)
    req.consumed_qty += scanned_qty
    req.save(update_fields=['consumed_qty'])

    # 3. Log the immutable transaction for genealogy/traceability
    pt = ProductionTransaction.objects.create(
        wo_id=wo_id,
        work_center_id=work_center_id,
        event_type=ProductionTransaction.EventType.MATERIAL_ISSUE,
        quantity=scanned_qty,
        batch_serial_ref=batch_ref,
        operator_id=operator_id
    )

    # 4. Trigger async cost rollup (Celery)
    execute_cost_rollup.delay(wo_id=str(wo_id), transaction_id=str(pt.transaction_id))

    return pt

@transaction.atomic
def log_yield(wo_op_id: UUID, yield_qty: Decimal, operator_id: UUID) -> ProductionTransaction:
    """
    Logs good parts produced. PostgreSQL Trigger guards the sequence.
    """
    op = WOOperation.objects.select_for_update().get(pk=wo_op_id)
    
    try:
        op.yield_qty += yield_qty
        op.save(update_fields=['yield_qty'])
    except IntegrityError as e:
        if 'Sequence Violation' in str(e):
            raise BusinessRuleViolation("Sequence Violation: Cannot yield this operation before previous operation is completed.")
        raise

    pt = ProductionTransaction.objects.create(
        wo_id=op.wo_id,
        work_center_id=op.work_center_id,
        event_type=ProductionTransaction.EventType.YIELD,
        quantity=yield_qty,
        operator_id=operator_id
    )
    
    execute_cost_rollup.delay(wo_id=str(op.wo_id), transaction_id=str(pt.transaction_id))
    return pt

@transaction.atomic
def complete_work_order(wo_id: UUID) -> WorkOrder:
    """
    Attempts to close WO. DB Trigger 'trg_enforce_material_allocation' 
    guarantees completion fails if consumed < required.
    """
    wo = WorkOrder.objects.select_for_update().get(pk=wo_id)
    if wo.status == WorkOrder.WOStatus.COMPLETED:
        return wo
        
    try:
        wo.status = WorkOrder.WOStatus.COMPLETED
        wo.save(update_fields=['status', 'updated_at'])
        return wo
    except IntegrityError as e:
        if 'Material Allocation Hard-Stop' in str(e):
            raise BusinessRuleViolation("Cannot complete: Work Order has unmet material requirements.")
        raise