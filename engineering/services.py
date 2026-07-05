from uuid import UUID
from datetime import date
from decimal import Decimal
from django.db import transaction, IntegrityError
from psycopg2.extras import DateRange
from engineering.models import BOMHeader, BOMLine, Routing, EngineeringChangeOrder
from core.exceptions import BusinessRuleViolation, HierarchicalIntegrityError, ImmutableStateViolation

@transaction.atomic
def create_draft_bom(item_id: UUID, node_id: UUID, bom_type: str, revision_level: str) -> BOMHeader:
    """Instantiates a new DRAFT BOM."""
    try:
        return BOMHeader.objects.create(
            item_id=item_id,
            node_id=node_id,
            bom_type=bom_type,
            revision_level=revision_level,
            status=BOMHeader.BOMStatus.DRAFT
        )
    except IntegrityError:
        raise BusinessRuleViolation("A BOM with this Revision Level already exists for this Node and Item.")

@transaction.atomic
def add_bom_line(bom_id: UUID, component_item_id: UUID, quantity: Decimal, scrap_factor: Decimal, valid_from: date = None, valid_to: date = None) -> BOMLine:
    """
    Adds a component to a BOM.
    PostgreSQL triggers guard against Acyclic loops and Component Node constraints.
    """
    date_range = DateRange(valid_from, valid_to, bounds='[)') if valid_from or valid_to else None
    
    try:
        return BOMLine.objects.create(
            bom_id=bom_id,
            component_item_id=component_item_id,
            quantity=quantity,
            scrap_factor=scrap_factor,
            effectivity_dates=date_range
        )
    except IntegrityError as e:
        error_msg = str(e)
        if 'Acyclic BOM Violation' in error_msg:
            raise HierarchicalIntegrityError("Inserting this component creates an infinite loop.")
        elif 'Component Validation Failed' in error_msg:
            raise BusinessRuleViolation("Component does not have an ACTIVE Node Extension at this Node.")
        elif 'Immutability Lock' in error_msg:
            raise ImmutableStateViolation("Cannot add lines to an ACTIVE BOM.")
        raise BusinessRuleViolation(f"Database Integrity Error: {error_msg}")

@transaction.atomic
def draft_eco(target_bom_id: UUID, node_id: UUID, reason_code: str) -> EngineeringChangeOrder:
    """Generates a new ECO for governance review."""
    return EngineeringChangeOrder.objects.create(
        target_bom_id=target_bom_id,
        node_id=node_id,
        reason_code=reason_code,
        approval_status=EngineeringChangeOrder.ApprovalStatus.PENDING
    )

@transaction.atomic
def approve_eco(eco_id: UUID, effectivity_date: date) -> EngineeringChangeOrder:
    """
    Transitions ECO to APPROVED and sets the effectivity date.
    Execution happens via Celery.
    """
    eco = EngineeringChangeOrder.objects.select_for_update().get(pk=eco_id)
    if eco.approval_status != EngineeringChangeOrder.ApprovalStatus.PENDING:
        raise ImmutableStateViolation("Only PENDING ECOs can be approved.")
        
    eco.approval_status = EngineeringChangeOrder.ApprovalStatus.APPROVED
    eco.effectivity_date = effectivity_date
    eco.save(update_fields=['approval_status', 'effectivity_date', 'updated_at'])
    return eco