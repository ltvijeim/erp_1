from celery import shared_task
from uuid import UUID
from django.core.cache import cache
from mdm.models import Item

@shared_task
def invalidate_mdm_cache(entity_type: str, entity_id: str) -> None:
    """
    Listens for updates from mdm.services and actively invalidates Redis keys
    for Items or Business Partners, forcing the next selector read to fetch from DB.
    """
    cache_key = f"mdm:{entity_type}:{entity_id}"
    cache.delete(cache_key)
    print(f"DEBUG CACHE -> Invalidated: {cache_key}")

@shared_task
def warm_item_cache(item_id: str) -> None:
    """Hydrates the Redis cache immediately after a new item is created or updated."""
    item = Item.objects.filter(pk=item_id).first()
    if item:
        cache_key = f"mdm:item:{item_id}"
        cache.set(cache_key, item, timeout=3600)
        print(f"DEBUG CACHE -> Warmed: {cache_key}")