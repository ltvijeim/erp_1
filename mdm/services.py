from typing import Optional, Any
from uuid import UUID
from django.db import transaction, IntegrityError
from core.exceptions import BusinessRuleViolation, HierarchicalIntegrityError
from mdm.models import Item, ItemNodeExtension, BusinessPartner, BPNodeRole
from mdm.tasks import warm_item_cache, invalidate_mdm_cache

@transaction.atomic
def create_global_item(sku: str, item_class: str, base_uom: str, description: str, traceability: str) -> Item:
    """Instantiates a Global Item and queues a Celery task to warm its cache."""
    try:
        item = Item.objects.create(
            sku=sku,
            item_class=item_class,
            base_uom=base_uom,
            global_description=description,
            traceability_type=traceability
        )
        # Asynchronously warm the Redis cache
        warm_item_cache.delay(str(item.item_id))
        return item
    except IntegrityError:
        raise BusinessRuleViolation(f"Item SKU '{sku}' already exists.")

@transaction.atomic
def extend_item_to_node(item_id: UUID, node_id: UUID, costing_method: str, replenishment_rule: str) -> ItemNodeExtension:
    """
    Localizes an item to a Node.
    Uses 'select_for_update()' on the Item to prevent concurrent "Phantom Reads" 
    from procurement/sales modules while the extension is being established.
    """
    # Prevent phantom reads by locking the primary master item
    item = Item.objects.select_for_update().filter(pk=item_id).first()
    if not item:
        raise BusinessRuleViolation("The Global Master Item does not exist.")
        
    try:
        extension = ItemNodeExtension.objects.create(
            item=item,
            node_id=node_id,
            costing_method=costing_method,
            replenishment_rule=replenishment_rule
        )
        return extension
    except IntegrityError:
        raise BusinessRuleViolation(f"This Item has already been extended to target Node.")

@transaction.atomic
def update_base_uom(item_id: UUID, new_uom: str) -> Item:
    """
    Attempts to update Base UoM.
    Will implicitly hit DB Trigger 'trg_items_protect_uom'. If the item is ACTIVE 
    and transacted, PostgreSQL raises an IntegrityError. Service translates this 
    to a BusinessRuleViolation exception.
    """
    item = Item.objects.select_for_update().filter(pk=item_id).first()
    if not item:
        raise BusinessRuleViolation("Item not found.")

    try:
        item.base_uom = new_uom
        item.save(update_fields=['base_uom', 'updated_at'])
        
        # Instantly invalidate the cache
        invalidate_mdm_cache.delay('item', str(item_id))
        return item
    except IntegrityError as e:
        if 'Base UoM cannot be modified' in str(e):
            raise BusinessRuleViolation("Base UoM is locked. Item status is ACTIVE and cannot be mutated.")
        raise

@transaction.atomic
def create_business_partner(bp_number: str, legal_name: str, parent_bp_id: Optional[UUID] = None) -> BusinessPartner:
    """Instantiates a Universal BP. DB Trigger 'trg_bp_prevent_loops' guards against circular hierarchy."""
    try:
        bp = BusinessPartner.objects.create(
            bp_number=bp_number,
            legal_name=legal_name,
            parent_bp_id=parent_bp_id
        )
        return bp
    except IntegrityError as e:
        if 'Cyclic Reference Violation' in str(e):
            raise HierarchicalIntegrityError("Corporate parent assignment creates an infinite loop.")
        raise BusinessRuleViolation(f"Business Partner '{bp_number}' already exists.")

@transaction.atomic
def assign_bp_role_to_node(bp_id: UUID, node_id: UUID, role: str, financial_terms: str) -> BPNodeRole:
    """Assigns a BP as a Supplier, Customer, etc., to a specific Node."""
    try:
        role_assignment = BPNodeRole.objects.create(
            bp_id=bp_id,
            node_id=node_id,
            bp_role=role,
            financial_terms=financial_terms
        )
        return role_assignment
    except IntegrityError:
        raise BusinessRuleViolation("This role has already been assigned to this Business Partner at this Node.")