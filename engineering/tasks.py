from celery import shared_task
from django.db import transaction
from engineering.models import EngineeringChangeOrder, BOMHeader

@shared_task(bind=True, max_retries=3)
def execute_eco_transition(self, eco_id: str) -> None:
    """
    The background engine for "Strict Effectivity Handoffs".
    Locks the ECO, obsoletes the old revision, activates the new BOM.
    """
    with transaction.atomic():
        # Lock ECO
        eco = EngineeringChangeOrder.objects.select_for_update().get(pk=eco_id)
        
        if eco.approval_status != EngineeringChangeOrder.ApprovalStatus.APPROVED:
            return  # Safety abort
            
        target_bom = eco.target_bom
        
        # 1. Obsolete the previous active BOM for this specific Node, Item, and Type
        previous_boms = BOMHeader.objects.filter(
            item_id=target_bom.item_id,
            node_id=target_bom.node_id,
            bom_type=target_bom.bom_type,
            status=BOMHeader.BOMStatus.ACTIVE
        ).exclude(pk=target_bom.pk)
        
        for p_bom in previous_boms:
            p_bom.status = BOMHeader.BOMStatus.OBSOLETE
            p_bom.save(update_fields=['status', 'updated_at'])
            
        # 2. Activate the new target BOM
        target_bom.status = BOMHeader.BOMStatus.ACTIVE
        target_bom.save(update_fields=['status', 'updated_at'])
        
        # 3. Mark ECO Executed
        eco.approval_status = EngineeringChangeOrder.ApprovalStatus.EXECUTED
        eco.save(update_fields=['approval_status', 'updated_at'])
        
        # At this point, we would fire events to Finance/MES to recalculate Standard Costing.
        print(f"DEBUG ECO -> Executed transition for ECO {eco.eco_id}")