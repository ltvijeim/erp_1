from typing import Any, Optional
from uuid import UUID
from django.db.models import QuerySet
from django.db import connection
from platform_app.models import Node, NodeSetting, NodeAccessAssignment

def get_node_by_id(node_id: UUID) -> Optional[Node]:
    """Fetches a specific Node and pre-fetches its immediate settings."""
    return Node.objects.prefetch_related('settings').filter(pk=node_id).first()

def get_node_descendants(node_id: UUID, include_self: bool = True) -> QuerySet[Node]:
    """
    Leverages PostgreSQL ltree '<@' (is descendant) operator to fetch 
    all child/grandchild nodes within milliseconds.
    """
    node = Node.objects.filter(pk=node_id).only('lineage_path').first()
    if not node or not node.lineage_path:
        return Node.objects.none()
    
    # Raw SQL execution for ltree parameter matching
    qs = Node.objects.extra(
        where=["lineage_path <@ %s"],
        params=[node.lineage_path]
    )
    if not include_self:
        qs = qs.exclude(pk=node_id)
    return qs

def resolve_node_setting(node_id: UUID, setting_key: str) -> Optional[dict[str, Any]]:
    """
    Contextual Inheritance Engine: Traverses up the ltree lineage_path 
    and finds the closest setting definition.
    """
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT s.setting_value 
            FROM platform_nodes n
            JOIN platform_node_settings s ON s.node_id = n.node_id
            WHERE n.lineage_path @> (SELECT lineage_path FROM platform_nodes WHERE node_id = %s)
              AND s.setting_key = %s
            ORDER BY nlevel(n.lineage_path) DESC
            LIMIT 1;
        """, [str(node_id), setting_key])
        row = cursor.fetchone()
        return row[0] if row else None

def check_user_node_authorization(user_id: UUID, target_node_id: UUID, required_role: str = None) -> bool:
    """
    Evaluates if the user has direct or cascaded access to the target node.
    """
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT EXISTS (
                SELECT 1
                FROM platform_node_access_assignments auth
                JOIN platform_nodes auth_node ON auth_node.node_id = auth.node_id
                JOIN platform_nodes target_node ON target_node.node_id = %s
                WHERE auth.user_id = %s
                  AND (%s IS NULL OR auth.role = %s)
                  AND (
                      auth.node_id = target_node.node_id
                      OR (auth.cascade_access = TRUE AND auth_node.lineage_path @> target_node.lineage_path)
                  )
            );
        """, [str(target_node_id), str(user_id), required_role, required_role])
        return cursor.fetchone()[0]