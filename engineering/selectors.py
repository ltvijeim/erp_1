from typing import Optional, List
from uuid import UUID
from datetime import date
from django.db import connection
from django.db.models import QuerySet
from engineering.models import BOMHeader, BOMLine, Routing

def get_active_bom_for_node(item_id: UUID, node_id: UUID) -> Optional[BOMHeader]:
    """
    Node-Based Resolution (Logical Inheritance).
    Finds the active BOM for the specified node. If none exists, traverses up the 
    platform ltree path to find a Regional or Global BOM.
    """
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT bh.bom_id 
            FROM eng.bom_headers bh
            JOIN platform_nodes n ON bh.node_id = n.node_id
            WHERE bh.item_id = %s
              AND bh.status = 'ACTIVE'
              AND n.lineage_path @> (SELECT lineage_path FROM platform_nodes WHERE node_id = %s)
            ORDER BY nlevel(n.lineage_path) DESC
            LIMIT 1;
        """, [str(item_id), str(node_id)])
        row = cursor.fetchone()
        
    if row:
        return BOMHeader.objects.get(pk=row[0])
    return None

def get_bom_explosion(bom_id: UUID, target_date: date) -> QuerySet[BOMLine]:
    """
    Retrieves the active ingredients for a given date.
    Filters the PostgreSQL daterange using the @> (contains) operator.
    """
    # Using Django's ORM mapped to Postgres daterange queries
    return BOMLine.objects.filter(
        bom_id=bom_id,
        effectivity_dates__contains=target_date
    ).select_related('component_item')

def get_routing_sequence(bom_id: UUID) -> QuerySet[Routing]:
    """Fetches the sequential manufacturing steps for MES execution."""
    return Routing.objects.filter(bom_id=bom_id).order_by('operation_seq')