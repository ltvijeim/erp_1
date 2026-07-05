import uuid
from django.db import models
from django.db.models import UniqueConstraint
from django.contrib.postgres.fields import DateRangeField
from core.models import TimeStampedModel
from platform_app.models import Node
from mdm.models import Item

class BOMHeader(TimeStampedModel):
    """
    The Master Recipe.
    Defines a specific revision of how an Item is built at a specific Node.
    """
    class BOMType(models.TextChoices):
        MANUFACTURING = 'MANUFACTURING', 'Manufacturing'
        ENGINEERING = 'ENGINEERING', 'Engineering'
        KIT = 'KIT', 'Kit'
        PHANTOM = 'PHANTOM', 'Phantom'

    class BOMStatus(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        ACTIVE = 'ACTIVE', 'Active'
        OBSOLETE = 'OBSOLETE', 'Obsolete'

    bom_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    item = models.ForeignKey(Item, on_delete=models.RESTRICT, related_name='boms')
    node = models.ForeignKey(Node, on_delete=models.RESTRICT, related_name='node_boms')
    revision_level = models.CharField(max_length=50)
    bom_type = models.CharField(max_length=50, choices=BOMType.choices)
    status = models.CharField(max_length=30, choices=BOMStatus.choices, default=BOMStatus.DRAFT)

    class Meta:
        db_table = '"eng"."bom_headers"'
        constraints = [
            UniqueConstraint(fields=['item', 'node', 'revision_level'], name='uq_item_node_revision')
        ]
        indexes = [
            models.Index(fields=['item', 'node'], name='idx_bom_headers_item_node'),
            models.Index(fields=['status'], name='idx_bom_headers_status'),
        ]

class BOMLine(models.Model):
    """
    The Ingredients.
    The specific components consumed to build the BOM Header.
    """
    bom_line_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bom = models.ForeignKey(BOMHeader, on_delete=models.CASCADE, related_name='lines')
    component_item = models.ForeignKey(Item, on_delete=models.RESTRICT, related_name='used_in_boms')
    quantity = models.DecimalField(max_digits=19, decimal_places=4)
    scrap_factor = models.DecimalField(max_digits=5, decimal_places=4, default=0.0000)
    
    # PostgreSQL native daterange. Null indicates infinite bounds.
    effectivity_dates = DateRangeField(null=True, blank=True) 

    class Meta:
        db_table = '"eng"."bom_lines"'
        indexes = [
            models.Index(fields=['component_item'], name='idx_bom_lines_component'),
        ]

class Routing(models.Model):
    """
    The Instructions.
    The sequence of operations required to transform the BOM Lines into the finished Item.
    """
    routing_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bom = models.ForeignKey(BOMHeader, on_delete=models.CASCADE, related_name='routings')
    node = models.ForeignKey(Node, on_delete=models.RESTRICT, related_name='site_routings')
    operation_seq = models.IntegerField()
    
    # work_center MUST be a Node of type 'WORK_CENTER'
    work_center = models.ForeignKey(Node, on_delete=models.RESTRICT, related_name='work_center_routings')
    standard_time = models.DecimalField(max_digits=19, decimal_places=4)

    class Meta:
        db_table = '"eng"."routings"'
        constraints = [
            UniqueConstraint(fields=['bom', 'operation_seq'], name='uq_routing_seq')
        ]

class EngineeringChangeOrder(TimeStampedModel):
    """
    The Governance Vehicle.
    Controls the immutable lifecycle of BOMs and Routings.
    """
    class ReasonCode(models.TextChoices):
        COST_REDUCTION = 'COST_REDUCTION', 'Cost Reduction'
        QUALITY_FIX = 'QUALITY_FIX', 'Quality Fix'
        OBSOLESCENCE = 'OBSOLESCENCE', 'Obsolescence'
        NPI = 'NPI', 'New Product Introduction'

    class ApprovalStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'
        EXECUTED = 'EXECUTED', 'Executed'

    eco_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    node = models.ForeignKey(Node, on_delete=models.RESTRICT, related_name='ecos')
    reason_code = models.CharField(max_length=50, choices=ReasonCode.choices)
    target_bom = models.ForeignKey(BOMHeader, on_delete=models.RESTRICT, related_name='ecos')
    approval_status = models.CharField(max_length=30, choices=ApprovalStatus.choices, default=ApprovalStatus.PENDING)
    effectivity_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = '"eng"."ecos"'