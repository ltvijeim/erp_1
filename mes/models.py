import uuid
from django.db import models
from django.db.models import UniqueConstraint
from core.models import TimeStampedModel
from platform_app.models import Node
from mdm.models import Item

class WorkCenter(models.Model):
    """
    The Resource Node.
    Extends the Global Node to define manufacturing capacity and standard costs.
    """
    class ResourceType(models.TextChoices):
        MACHINE = 'MACHINE', 'Machine'
        LABOR_POOL = 'LABOR_POOL', 'Labor Pool'
        SUBCONTRACTOR = 'SUBCONTRACTOR', 'Subcontractor'

    node = models.OneToOneField(Node, primary_key=True, on_delete=models.CASCADE, related_name='work_center_profile')
    resource_type = models.CharField(max_length=50, choices=ResourceType.choices)
    standard_cost_rate = models.DecimalField(max_digits=19, decimal_places=4, default=0.0000)
    capacity_hrs_day = models.DecimalField(max_digits=5, decimal_places=2)  # DB CHECK: 0-24

    class Meta:
        db_table = '"mes"."work_centers"'

class WorkOrder(TimeStampedModel):
    """
    The Execution Ticket.
    Authorizes the transformation of materials into a finished good.
    """
    class WOStatus(models.TextChoices):
        PLANNED = 'PLANNED', 'Planned'
        RELEASED = 'RELEASED', 'Released'
        IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
        COMPLETED = 'COMPLETED', 'Completed'
        CLOSED = 'CLOSED', 'Closed'

    wo_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    node = models.ForeignKey(Node, on_delete=models.RESTRICT, related_name='work_orders')
    item = models.ForeignKey(Item, on_delete=models.RESTRICT, related_name='manufactured_orders')
    target_quantity = models.DecimalField(max_digits=19, decimal_places=4)
    status = models.CharField(max_length=30, choices=WOStatus.choices, default=WOStatus.PLANNED)
    actual_cost = models.DecimalField(max_digits=19, decimal_places=4, default=0.0000)

    class Meta:
        db_table = '"mes"."work_orders"'
        indexes = [
            models.Index(fields=['status'], name='idx_wo_status'),
            models.Index(fields=['node'], name='idx_wo_node'),
        ]

class WOOperation(models.Model):
    """
    The Routing Snapshot.
    Locks in the manufacturing steps for this specific Work Order.
    """
    wo_op_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    wo = models.ForeignKey(WorkOrder, on_delete=models.CASCADE, related_name='operations')
    operation_seq = models.IntegerField()
    work_center = models.ForeignKey(WorkCenter, on_delete=models.RESTRICT, related_name='scheduled_operations')
    yield_qty = models.DecimalField(max_digits=19, decimal_places=4, default=0.0000)
    scrap_qty = models.DecimalField(max_digits=19, decimal_places=4, default=0.0000)

    class Meta:
        db_table = '"mes"."wo_operations"'
        constraints = [
            UniqueConstraint(fields=['wo', 'operation_seq'], name='uq_wo_op_seq')
        ]

class WOMaterialRequirement(models.Model):
    """
    The Pick List (BOM Snapshot).
    Locks in the specific ingredients required for this Work Order.
    """
    requirement_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    wo = models.ForeignKey(WorkOrder, on_delete=models.CASCADE, related_name='material_requirements')
    component_item = models.ForeignKey(Item, on_delete=models.RESTRICT, related_name='required_in_wos')
    required_qty = models.DecimalField(max_digits=19, decimal_places=4)
    consumed_qty = models.DecimalField(max_digits=19, decimal_places=4, default=0.0000)

    class Meta:
        db_table = '"mes"."wo_material_requirements"'
        constraints = [
            UniqueConstraint(fields=['wo', 'component_item'], name='uq_wo_req_item')
        ]

class ProductionTransaction(TimeStampedModel):
    """
    The Immutable Execution Log.
    Records every scanner beep, physical material issue, and labor hour.
    """
    class EventType(models.TextChoices):
        SETUP = 'SETUP', 'Setup'
        RUN = 'RUN', 'Run'
        MATERIAL_ISSUE = 'MATERIAL_ISSUE', 'Material Issue'
        SCRAP = 'SCRAP', 'Scrap'
        YIELD = 'YIELD', 'Yield'

    transaction_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    wo = models.ForeignKey(WorkOrder, on_delete=models.RESTRICT, related_name='transactions')
    work_center = models.ForeignKey(WorkCenter, on_delete=models.RESTRICT, related_name='executed_transactions')
    event_type = models.CharField(max_length=30, choices=EventType.choices)
    quantity = models.DecimalField(max_digits=19, decimal_places=4, default=0.0000)
    labor_hours = models.DecimalField(max_digits=19, decimal_places=4, default=0.0000)
    batch_serial_ref = models.CharField(max_length=100, null=True, blank=True)
    operator_id = models.UUIDField(db_index=True)  # System Auth User ID

    class Meta:
        db_table = '"mes"."production_transactions"'
        indexes = [
            models.Index(fields=['batch_serial_ref'], name='idx_pt_batch'),
        ]