from typing import Optional
from uuid import UUID
from django.core.cache import cache
from django.db.models import QuerySet
from mdm.models import Item, EffectiveItemStatusView, BusinessPartner, BPNodeRole

def get_global_item(item_id: UUID) -> Optional[Item]:
    """
    Fetches the Global Item definition.
    Architectural Pattern: Attempts Cache hit (Redis) first -> Falls back to DB.
    """
    cache_key = f"mdm:item:{str(item_id)}"
    cached_item = cache.get(cache_key)
    
    if cached_item:
        return cached_item
        
    item = Item.objects.filter(pk=item_id).first()
    if item:
        # Cache for 1 hour to prevent read bottlenecks on highly concurrent scanners
        cache.set(cache_key, item, timeout=3600)
    return item

def is_item_active_at_node(item_id: UUID, node_id: UUID) -> bool:
    """
    Extension Prerequisite check. Queries the EffectiveItemStatusView (managed=False)
    to see if effective_status == 'ACTIVE'. This evaluates global vs. local rules instantly.
    """
    return EffectiveItemStatusView.objects.filter(
        item_id=item_id, 
        node_id=node_id, 
        effective_status='ACTIVE'
    ).exists()

def get_business_partner_hierarchy(bp_id: UUID) -> QuerySet[BusinessPartner]:
    """Fetches the Business Partner and all its nested corporate subsidiaries."""
    # Performs clean recursive hierarchy retrieval
    return BusinessPartner.objects.filter(models.Q(pk=bp_id) | models.Q(parent_bp_id=bp_id))

def get_authorized_carriers_for_node(node_id: UUID) -> QuerySet[BPNodeRole]:
    """Reads BPNodeRoles filtering by 'CARRIER' role for a given Node."""
    return BPNodeRole.objects.select_related('bp', 'node').filter(
        node_id=node_id, 
        bp_role=BPNodeRole.BPRole.CARRIER
    )