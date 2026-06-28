import uuid
from django.db import models
from django.db.models import UniqueConstraint
from core.models import TimeStampedModel
from platform_app.models import Node

class Item(TimeStampedModel):
    """
    The Universal "What" (Global Master).
    Immutable core characteristics of a product/service.
    """
    class ItemClass(models.TextChoices):
        INVENTORY = 'INVENTORY', 'Inventory'
        SERVICE = 'SERVICE', 'Service'
        RAW_MATERIAL = 'RAW_MATERIAL', 'Raw Material'
        ASSEMBLY = 'ASSEMBLY', 'Assembly'
        PHANTOM = 'PHANTOM', 'Phantom'

    class TraceabilityType(models.TextChoices):
        NONE = 'NONE', 'None'
        BATCH = 'BATCH', 'Batch Tracked'
        SERIAL = 'SERIAL', 'Serial Tracked'

    class GlobalStatus(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Active'
        INACTIVE = 'INACTIVE', 'Inactive'
        IN_DEVELOPMENT = 'IN_DEVELOPMENT', 'In Development'

    item_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sku = models.CharField(max_length=100, unique=True)
    item_class = models.CharField(max_length=50, choices=ItemClass.choices)
    base_uom = models.CharField(max_length=20)  # Immutable once transacted
    global_description = models.TextField()
    traceability_type = models.CharField(
        max_length=20, 
        choices=TraceabilityType.choices, 
        default=TraceabilityType.NONE
    )
    global_status = models.CharField(
        max_length=30, 
        choices=GlobalStatus.choices, 
        default=GlobalStatus.IN_DEVELOPMENT
    )

    class Meta:
        db_table = '"mdm"."items"'
        indexes = [
            models.Index(fields=['global_status'], name='idx_items_status'),
            models.Index(fields=['item_class'], name='idx_items_class'),
        ]

    def __str__(self) -> str:
        return f"{self.sku} ({self.item_class})"


class ItemNodeExtension(TimeStampedModel):
    """
    The Local "How".
    Links a Global Item to a specific Node, defining local operational behavior.
    """
    class LocalStatus(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Active'
        DISCONTINUED = 'DISCONTINUED', 'Discontinued'
        PHASE_OUT = 'PHASE_OUT', 'Phase Out'
        INACTIVE = 'INACTIVE', 'Inactive'

    class CostingMethod(models.TextChoices):
        STANDARD = 'STANDARD', 'Standard'
        FIFO = 'FIFO', 'FIFO'
        MOVING_AVERAGE = 'MOVING_AVERAGE', 'Moving Average'

    class ReplenishmentRule(models.TextChoices):
        MAKE_TO_STOCK = 'MAKE_TO_STOCK', 'Make to Stock'
        MAKE_TO_ORDER = 'MAKE_TO_ORDER', 'Make to Order'
        BUY_TO_ORDER = 'BUY_TO_ORDER', 'Buy to Order'
        NONE = 'NONE', 'None'

    extension_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='node_extensions')
    node = models.ForeignKey(Node, on_delete=models.CASCADE, related_name='item_extensions')
    local_status = models.CharField(
        max_length=30, 
        choices=LocalStatus.choices, 
        default=LocalStatus.ACTIVE
    )
    costing_method = models.CharField(max_length=30, choices=CostingMethod.choices)
    replenishment_rule = models.CharField(max_length=30, choices=ReplenishmentRule.choices)

    class Meta:
        db_table = '"mdm"."item_node_extensions"'
        constraints = [
            UniqueConstraint(fields=['item', 'node'], name='uq_item_node')
        ]
        indexes = [
            models.Index(fields=['node'], name='idx_item_ext_node'),
        ]


class EffectiveItemStatusView(models.Model):
    """
    Unmanaged model mapping to PostgreSQL View 'mdm.vw_effective_item_status'.
    Resolves the 'Global vs. Local Status Conflict' rule mathematically.
    """
    extension_id = models.UUIDField(primary_key=True)
    item_id = models.UUIDField()
    node_id = models.UUIDField()
    global_status = models.CharField(max_length=30)
    raw_local_status = models.CharField(max_length=30)
    effective_status = models.CharField(max_length=30)
    traceability_type = models.CharField(max_length=20)

    class Meta:
        managed = False
        db_table = '"mdm"."vw_effective_item_status"'


class BusinessPartner(TimeStampedModel):
    """
    The Universal "Who".
    Unified entity for Suppliers, Customers, Carriers, and corporate hierarchies.
    """
    bp_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bp_number = models.CharField(max_length=100, unique=True)
    legal_name = models.CharField(max_length=255)
    tax_vat_id = models.CharField(max_length=100, null=True, blank=True)
    parent_bp = models.ForeignKey(
        'self', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='subsidiaries'
    )

    class Meta:
        db_table = '"mdm"."business_partners"'

    def __str__(self) -> str:
        return f"{self.legal_name} ({self.bp_number})"


class BPNodeRole(TimeStampedModel):
    """
    The Local Relationship.
    Defines how a Node interacts with a BP (e.g., Supplier to factory, Customer to retail).
    """
    class BPRole(models.TextChoices):
        CUSTOMER = 'CUSTOMER', 'Customer'
        SUPPLIER = 'SUPPLIER', 'Supplier'
        CARRIER = 'CARRIER', 'Carrier'
        EMPLOYEE = 'EMPLOYEE', 'Employee'

    role_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bp = models.ForeignKey(BusinessPartner, on_delete=models.CASCADE, related_name='node_roles')
    node = models.ForeignKey(Node, on_delete=models.CASCADE, related_name='bp_roles')
    bp_role = models.CharField(max_length=50, choices=BPRole.choices)
    financial_terms = models.CharField(max_length=50)  # e.g., 'NET_30'

    class Meta:
        db_table = '"mdm"."bp_node_roles"'
        constraints = [
            UniqueConstraint(fields=['bp', 'node', 'bp_role'], name='uq_bp_node_role')
        ]