from uuid import UUID
from typing import Any
from django.db import transaction, IntegrityError
from platform_app.models import Node, NodeSetting, NodeAccessAssignment
from core.exceptions import HierarchicalIntegrityError, BusinessRuleViolation

@transaction.atomic
def create_node(node_type: str, node_name: str, parent_node_id: UUID = None, status: str = Node.NodeStatus.PLANNED) -> Node:
    """
    Instantiates a new Node. Triggers DB implicitly to calculate ltree path.
    Enforces 'Law of the Root'.
    """
    try:
        node = Node.objects.create(
            node_type=node_type,
            node_name=node_name,
            parent_node_id=parent_node_id,
            status=status
        )
        return node
    except IntegrityError as e:
        if 'uq_one_root_node_allowed' in str(e):
            raise HierarchicalIntegrityError("The Law of the Root violated: A Root node already exists.")
        raise

@transaction.atomic
def update_node_parent(node_id: UUID, new_parent_node_id: UUID) -> Node:
    """
    Relocates a Node spatially. DB Trigger 'trg_nodes_prevent_loops' implicitly guards against Acyclic violations.
    """
    try:
        # We lock the node to prevent concurrent structural shifts
        node = Node.objects.select_for_update().get(pk=node_id)
        node.parent_node_id = new_parent_node_id
        node.save(update_fields=['parent_node_id', 'updated_at'])
        return node
    except IntegrityError as e:
        if 'Cyclic Reference Violation' in str(e):
            raise HierarchicalIntegrityError("Cannot set a node as its own parent or child.")
        raise

@transaction.atomic
def set_node_setting(node_id: UUID, setting_key: str, setting_value: dict[str, Any], is_override: bool = False) -> NodeSetting:
    """Creates or updates a Node Setting for contextual inheritance."""
    setting, _ = NodeSetting.objects.update_or_create(
        node_id=node_id,
        setting_key=setting_key,
        defaults={'setting_value': setting_value, 'is_override': is_override}
    )
    return setting

@transaction.atomic
def assign_node_access(user_id: UUID, node_id: UUID, role: str, cascade_access: bool = True) -> NodeAccessAssignment:
    """Grants a user access to a specific node layer."""
    try:
        assignment = NodeAccessAssignment.objects.create(
            user_id=user_id,
            node_id=node_id,
            role=role,
            cascade_access=cascade_access
        )
        return assignment
    except IntegrityError:
        raise BusinessRuleViolation("User already possesses this role at this exact Node.")