from celery import shared_task
from uuid import UUID
from django.db import transaction
from decimal import Decimal
from mes.models import WorkOrder, ProductionTransaction, WorkCenter

@shared_task(bind=True, max_retries=3)
def execute_cost_rollup(self, wo_id: str, transaction_id: str) -> None:
    """
    Cost Rollup Execution.
    Offloads multi-table JOINs and math from the API thread.
    """
    with transaction.atomic():
        pt = ProductionTransaction.objects.get(pk=transaction_id)
        wo = WorkOrder.objects.select_for_update().get(pk=wo_id)
        
        cost_increment = Decimal('0.0000')
        
        if pt.event_type == ProductionTransaction.EventType.MATERIAL_ISSUE:
            # 1. Look up component standard cost from mdm.item_node_extensions (mocked here for simplicity)
            # ext = ItemNodeExtension.objects.get(item_id=pt.component_item_id, node_id=wo.node_id)
            # cost_increment = pt.quantity * ext.standard_cost
            cost_increment = pt.quantity * Decimal('5.0000') # Placeholder value
            
        elif pt.event_type in [ProductionTransaction.EventType.RUN, ProductionTransaction.EventType.SETUP]:
            # 2. Look up Work Center Labor Rate
            wc = WorkCenter.objects.get(pk=pt.work_center_id)
            cost_increment = pt.labor_hours * wc.standard_cost_rate

        # 3. Apply atomic increment
        wo.actual_cost += cost_increment
        wo.save(update_fields=['actual_cost', 'updated_at'])
        
        print(f"DEBUG MES -> Rolled up ${cost_increment} to WO {wo_id}")