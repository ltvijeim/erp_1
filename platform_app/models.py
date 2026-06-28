import uuid
from django.db import models
from django.db.models import UniqueConstraint, Q
from core.models import TimeStampedModel
from core.fields import LtreeField
from django.conf import settings

class Node(TimeStampedModel):
    """
    The Universal Organizational Unit.
    Represents the spatial and logical boundaries of the enterprise.
    """
    class NodeType(models.TextChoices):
        ENTERPRISE = 'ENTERPRISE', 'Enterprise'
        LEGAL_ENTITY = 'LEGAL_ENTITY', 'Legal Entity'
        REGION = 'REGION', 'Region'
        SITE = 'SITE', 'Site'
        ZONE = 'ZONE', 'Zone'
        BIN = 'BIN', 'Bin'
        WORK_CENTER = 'WORK_CENTER', 'Work Center'
        LPN = 'LPN', 'License Plate Number'

    class NodeStatus(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Active'
        INACTIVE = 'INACTIVE', 'Inactive'
        SUSPENDED = 'SUSPENDED', 'Suspended'
        PLANNED = 'PLANNED', 'Planned'

    node_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    parent_node = models.ForeignKey(
        'self',
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name='child_nodes'
    )
    node_type = models.CharField(max_length=50, choices=NodeType.choices)
    node_name = models.CharField(max_length=255)
    
    # Materialized path maintained purely by PostgreSQL DB Triggers
    lineage_path = LtreeField(null=True, blank=True) 
    
    status = models.CharField(
        max_length=30, 
        choices=NodeStatus.choices, 
        default=NodeStatus.PLANNED
    )

    class Meta:
        db_table = 'platform_nodes' # Naming convention for the monolith
        constraints = [
            # The Law of the Root: Only one node can have a NULL parent
            UniqueConstraint(
                fields=['parent_node'],
                condition=Q(parent_node__isnull=True),
                name='uq_one_root_node_allowed'
            ),
        ]
        indexes = [
            models.Index(fields=['node_type'], name='idx_nodes_node_type'),
            models.Index(fields=['status'], name='idx_nodes_status'),
        ]

class NodeSetting(TimeStampedModel):
    """
    The Inheritance Engine. Key-Value pairs that cascade down the Node hierarchy.
    """
    setting_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    node = models.ForeignKey(Node, on_delete=models.CASCADE, related_name='settings')
    setting_key = models.CharField(max_length=100)
    setting_value = models.JSONField()
    is_override = models.BooleanField(default=False)

    class Meta:
        db_table = 'platform_node_settings'
        constraints = [
            UniqueConstraint(fields=['node', 'setting_key'], name='uq_node_setting_key')
        ]

class NodeAccessAssignment(models.Model):
    """
    Security Scoping. Maps a physical identity (user_id) to a location/boundary (node_id).
    """
    assignment_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='node_access')
    node = models.ForeignKey(Node, on_delete=models.CASCADE, related_name='access_assignments')
    role = models.CharField(max_length=100)
    cascade_access = models.BooleanField(default=True)
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'platform_node_access_assignments'
        constraints = [
            UniqueConstraint(fields=['user', 'node', 'role'], name='uq_user_node_role')
        ]