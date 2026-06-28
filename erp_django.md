As the Principal Software Architect, I will establish the overarching Django project topology. Aligning with Domain-Driven Design (DDD) principles and the 11 bounded contexts outlined in your Conceptual Business Blueprint, we will map each domain to a specific, isolated Django app.
To enforce strict boundary contexts and prevent a "Big Ball of Mud" monolith, we will utilize a Modular Monolith architecture. Below is the high-level structural blueprint of the Django workspace.
1. High-Level Django Project Structure
enterprise_erp/
├── manage.py
├── enterprise_erp/                 # Project configuration
│   ├── settings/                   # Split settings (base.py, dev.py, prod.py)
│   ├── urls.py                     # Root URL routing (delegates to app urls.py)
│   ├── celery.py                   # Global Celery application configuration
│   └── wsgi.py / asgi.py
│
├── core/                           # Foundation Layer (No business logic)
│   ├── models.py                   # Abstract base models (UUID PKs, Timestamps)
│   ├── exceptions.py               # Standardized domain exceptions
│   └── utils.py                    # Shared utilities (e.g., custom ltree field definitions)
│
├── platform_app/                   # The Global Layer (Namespace: platform)
├── mdm/                            # Master Data Management (Namespace: mdm)
├── engineering/                    # Product Lifecycle (Namespace: eng)
├── mes/                            # Manufacturing Execution (Namespace: mes)
├── wms/                            # Supply Chain & Warehouse (Namespace: wms)
├── commercial/                     # Order-to-Cash & Logistics (Namespace: com)
├── procurement/                    # Procure-to-Pay (Namespace: proc)
├── cmms/                           # Asset Management (Namespace: cmms)
├── qms/                            # Quality Assurance (Namespace: qms)
├── hcm/                            # Human Capital (Namespace: hcm)
└── finance/                        # Scorekeeper & Compliance (Namespace: fin)

(Note: platform is a reserved keyword in standard Python, so we name the app folder platform_app but its app_label and DB schema will remain platform).

2. The Internal Anatomy of a Domain App (Strict Enforcement)
To satisfy the "Thin Views, Fat Services" mandate and the prohibition of the Django REST Framework (DRF), every single bounded context (app) will strictly adhere to the following file structure. No exceptions.
mdm/                                # Example using MDM domain
├── __init__.py
├── apps.py                         # App configuration (name = 'mdm')
├── urls.py                         # Internal API routing
├── models.py                       # STRICTLY Data schema, FKs, and Meta constraints
├── forms.py                        # STRICTLY Request payload validation (replaces DRF Serializers)
├── selectors.py                    # STRICTLY Read operations (Complex ORM, select_related)
├── services.py                     # STRICTLY Write operations (Business logic, state changes, DB locks)
├── tasks.py                        # STRICTLY Celery async workers (Cross-domain bridges)
└── views.py                        # STRICTLY HTTP lifecycle (Parses request -> calls service/selector -> JsonResponse)


3. Bounded Context Responsibilities (The 11 Pillars)
Here is exactly what each app is responsible for owning:
platform_app (Platform Infrastructure): Owns the Recursive Node Hierarchy (ltree), Contextual Inheritance (Node Settings), and Security Scoping (Access Assignments). Everything else in the ERP anchors here.
mdm (Master Data Management): Owns the global definitions of Items and Business Partners (Suppliers/Customers), and their localized extensions to specific Nodes.
engineering (Product Lifecycle): Owns Bills of Materials (BOMs), Routings (manufacturing steps), and Engineering Change Orders (ECOs).
mes (Manufacturing Execution): Owns Work Centers, Work Orders, and Production Transactions (Yield, Scrap, Labor logs).
wms (Warehouse Management): Owns the mathematical physical reality of the ERP. Inventory Positions, License Plate Numbers (LPNs as mobile nodes), and Warehouse Tasks.
commercial (Commercial & Logistics): Owns Sales Orders, Outbound Deliveries, and Shipments.
procurement (Procurement & Sourcing): Owns Purchase Requisitions, Purchase Orders, and Supplier Agreements (pricing/tolerances).
cmms (Maintenance & Asset Management): Owns Physical Assets, Meters, Maintenance Plans, and Maintenance Work Orders (MWOs).
qms (Quality Assurance & Control): The ultimate gatekeeper. Owns Inspection Plans, Inspection Orders, Results, and Non-Conformance Reports (NCRs).
hcm (Human Capital Management): Owns Positions (Budgets), Employees (encrypted PII), Certifications (lockout logic), and Time Logs.
finance (Financial & Compliance): The Scorekeeper. Owns the Chart of Accounts, Journal Entries (Headers/Lines), and Tax Rules.

4. Cross-Domain Architectural Rules (How Apps Communicate)
In a monolithic architecture, apps can easily become entangled. To maintain the purity of your conceptual blueprint, I will enforce the following Django coding rules:
Rule 1: Foreign Key Imports are Allowed. App A can import App B's models.py only to establish a ForeignKey or ManyToMany relationship.
Example: mes/models.py can import mdm.models.Item.
Rule 2: Read via Selectors. App A cannot write complex queries against App B's models in its own files. App A must call a function inside App B's selectors.py.
Example: commercial/services.py must call wms.selectors.get_allocatable_inventory(item_id) to check ATP (Available-to-Promise).
Rule 3: Mutate via Services. App A is strictly forbidden from calling .save(), .update(), or .delete() on App B's models. State changes must happen via a function in App B's services.py.
Rule 4: Asynchronous Subledger Bridging. Operational apps (wms, mes, commercial, procurement, hcm) will never synchronously import or call finance.services. They will fire Celery tasks (e.g., finance.tasks.post_goods_issue_subledger.delay(shipment_id)) to ensure API scanner latency stays under 100ms.

Next Steps
If you approve of this high-level project structure and the enforcement of the "Thin Views, Fat Services" file architecture, let me know which app/module you would like me to build out first.
I recommend we start with the core (Abstract Models) followed immediately by the platform_app (The Global Layer), as every other module requires the Node entity to exist.

As the Principal Software Architect, I will now define the core app.
This app acts as the Foundation Layer for the entire enterprise ERP. It contains no business logic of its own. Instead, it provides the abstract base models, custom PostgreSQL field mappings (like ltree for our recursive hierarchy), and standardized domain exceptions that will be universally inherited by the 11 operational bounded contexts.
Here is the architectural blueprint for the core app.
1. core/models.py
This file defines the abstract ORM components. Because the Conceptual Blueprint dictates exact TIMESTAMPTZ audit trails across every table, we abstract this to ensure DRY principles and strict database compliance.
import uuid
from django.db import models

class TimeStampedModel(models.Model):
    """
    Abstract base class providing self-updating 'created_at' and 'updated_at' fields.
    Maps directly to PostgreSQL TIMESTAMPTZ. 
    Assumes Django settings.USE_TZ = True.
    """
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class ERPBaseModel(TimeStampedModel):
    """
    Abstract base class combining UUID primary keys with timestamp audits.
    
    Architectural Note: 
    The physical DDL specifies explicit PK names (e.g., 'node_id', 'item_id').
    Child models will inherit this class and shadow the 'id' field with their
    specific explicit name if required, or utilize 'db_column' overrides.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


2. core/fields.py
The physical DDL specifically utilizes PostgreSQL's ltree extension for the Recursive Node Hierarchy's Materialized Path. Since standard Django does not include an ltree field out of the box, we declare the structural signature for it here.
(Note: Standard PostgreSQL fields like DateRangeField and JSONField are natively available in django.contrib.postgres and django.db.models, so they do not need custom definitions here).
from django.db import models

class LtreeField(models.TextField):
    """
    Custom Django ORM field mapping to the PostgreSQL 'ltree' extension.
    Crucial for ultra-fast spatial search and hierarchy resolution in the Platform layer.
    """
    description = "PostgreSQL ltree field for hierarchical materialized paths"

    def db_type(self, connection) -> str:
        ...
        
    def get_prep_value(self, value: str) -> str:
        ...

    def from_db_value(self, value: str, expression, connection) -> str:
        ...

3. core/exceptions.py
To enforce clean architecture, all apps must raise specific, predictable domain exceptions from their services.py layers. The views.py layer will catch these and translate them into appropriate HTTP status codes (e.g., 400 Bad Request, 409 Conflict, 423 Locked).
class ERPBaseException(Exception):
    """Root exception for all custom ERP domain errors."""
    pass


class ResourceLockedException(ERPBaseException):
    """
    Raised when a concurrency lock (SELECT FOR UPDATE SKIP LOCKED) fails to 
    acquire a resource. Typically translates to an HTTP 409 Conflict or 423 Locked.
    """
    pass


class ImmutableStateViolation(ERPBaseException):
    """
    Raised when an attempt is made to mutate a record that is mathematically sealed.
    Example: Editing a Journal Entry that is 'POSTED', or a BOM that is 'ACTIVE'.
    """
    pass


class HierarchicalIntegrityError(ERPBaseException):
    """
    Raised when a cyclic reference or invalid graph mutation is detected.
    Example: Attempting to assign a Node as its own parent.
    """
    pass


class BusinessRuleViolation(ERPBaseException):
    """
    Raised when a business constraint is broken.
    Example: Zero-Negative Inventory violation, or Over-Receipt Tolerance exceeded.
    """
    pass


class SecurityScopingException(ERPBaseException):
    """
    Raised when an action violates the Global Layer's Node Access Assignments.
    Example: A manager attempting to approve a PO outside their structural DoA.
    Translates to HTTP 403 Forbidden.
    """
    pass

4. core/utils.py
Shared architectural utilities.
from typing import Any
import uuid

def clean_uuid_for_ltree(raw_uuid: uuid.UUID) -> str:
    """
    The ltree extension expects labels to match the regex ^[A-Za-z0-9_]{1,256}$.
    Raw UUIDs contain hyphens which are illegal in ltree.
    This utility strips hyphens to generate a clean, safe hexadecimal string.
    """
    ...

def build_error_response(message: str, code: str, details: dict[str, Any] = None) -> dict[str, Any]:
    """
    Standardizes the error payload structure returned by all JsonResponse handlers
    across the 11 domain bounded contexts.
    """
    ...


Architectural Review
No Business Logic: The core layer acts purely as scaffolding.
Database Alignment: TimeStampedModel directly satisfies the created_at and updated_at TIMESTAMPTZ rules specified in every table of your DDL blueprint.
Strict Concurrency Prep: ResourceLockedException sets the stage for the wms and mes apps which will rely heavily on select_for_update() and nowait=True / skip_locked=True.
Next Step:
If the core foundation meets your approval, I recommend we proceed to the platform_app (The Global Layer). We will translate the platform.nodes, platform.node_settings, and platform.node_access_assignments DDL into strict Django models and define the signatures for Contextual Inheritance and Security Scoping. Shall we proceed?

As the Principal Software Architect, I will now define the platform_app (The Global Layer).
This app acts as the spatial and organizational nervous system of the ERP. Because it handles the highly recursive node hierarchy, we will map the PostgreSQL triggers and ltree functionality directly into our Django architecture. The API will rely on standard Django forms for validation (as DRF is strictly prohibited) and will separate reads (selectors.py) from writes (services.py).
Here is the strict architectural blueprint for the platform_app.
1. platform_app/models.py
This file maps the Physical DDL exactly into the Django ORM. We utilize Meta.constraints to enforce data integrity directly at the DB level, protecting us from application-level race conditions.
import uuid
from django.db import models
from django.db.models import CheckConstraint, Q, UniqueConstraint
from django.contrib.postgres.fields import JSONField  # or models.JSONField in Django 3.1+
from core.models import TimeStampedModel
from core.fields import LtreeField


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
    lineage_path = LtreeField()  # Maintained by PostgreSQL DB Triggers
    status = models.CharField(max_length=30, choices=NodeStatus.choices, default=NodeStatus.PLANNED)

    class Meta:
        db_table = 'platform\".\"nodes'
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
            # Note: GiST index for lineage_path is managed via raw SQL / migrations
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
        db_table = 'platform\".\"node_settings'
        constraints = [
            UniqueConstraint(fields=['node', 'setting_key'], name='uq_node_setting_key')
        ]


class NodeAccessAssignment(models.Model):
    """
    Security Scoping. Maps a physical identity (user_id) to a location/boundary (node_id).
    """
    assignment_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_id = models.UUIDField(db_index=True)  # References system Auth User ID externally
    node = models.ForeignKey(Node, on_delete=models.CASCADE, related_name='access_assignments')
    role = models.CharField(max_length=100)
    cascade_access = models.BooleanField(default=True)
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'platform\".\"node_access_assignments'
        constraints = [
            UniqueConstraint(fields=['user_id', 'node', 'role'], name='uq_user_node_role')
        ]

2. platform_app/selectors.py
These functions strictly handle database reads. They encapsulate complex recursive CTEs or ltree logic to prevent heavy business logic from leaking into the views.py.
from typing import Any, Optional
from uuid import UUID
from django.db.models import QuerySet
from platform_app.models import Node, NodeSetting, NodeAccessAssignment

def get_node_by_id(node_id: UUID) -> Node:
    """Fetches a specific Node and pre-fetches its immediate settings."""
    ...

def resolve_node_setting(node_id: UUID, setting_key: str) -> Optional[dict[str, Any]]:
    """
    Contextual Inheritance Engine: Evaluates the DB 'platform.fn_resolve_node_setting'
    to traverse up the ltree lineage_path and find the closest setting definition.
    Returns the JSON value if found, or None.
    """
    ...

def check_user_node_authorization(user_id: UUID, target_node_id: UUID, required_role: str = None) -> bool:
    """
    Security Scoping Engine: Evaluates the DB 'platform.fn_check_user_node_authorization'.
    Returns True if the user has direct or cascaded access to the target node.
    """
    ...

def get_node_descendants(node_id: UUID, include_self: bool = True) -> QuerySet[Node]:
    """
    Leverages PostgreSQL ltree '@>' operator to fetch all child/grandchild nodes
    within milliseconds. Prevents recursive N+1 ORM queries.
    """
    ...

3. platform_app/services.py
Strictly state-changing logic. These functions represent the "Fat Services" where we orchestrate data mutations. No HTTP context (request) is allowed here.
from uuid import UUID
from typing import Any
from platform_app.models import Node, NodeSetting, NodeAccessAssignment

def create_node(
    node_type: str, 
    node_name: str, 
    parent_node_id: UUID = None, 
    status: str = 'PLANNED'
) -> Node:
    """
    Instantiates a new Node. 
    Triggers DB 'trg_nodes_build_lineage' implicitly to calculate ltree path.
    Enforces 'Law of the Root' if parent_node_id is None.
    """
    ...

def update_node_parent(node_id: UUID, new_parent_node_id: UUID) -> Node:
    """
    Relocates a Node spatially. 
    DB Trigger 'trg_nodes_prevent_loops' implicitly guards against Acyclic violations.
    Catches IntegrityError and raises domain-specific HierarchicalIntegrityError.
    """
    ...

def set_node_setting(
    node_id: UUID, 
    setting_key: str, 
    setting_value: dict[str, Any], 
    is_override: bool = False
) -> NodeSetting:
    """
    Creates or updates a Node Setting for contextual inheritance.
    """
    ...

def assign_node_access(
    user_id: UUID, 
    node_id: UUID, 
    role: str, 
    cascade_access: bool = True
) -> NodeAccessAssignment:
    """
    Grants a user access to a specific node layer.
    """
    ...

def revoke_node_access(assignment_id: UUID) -> None:
    """
    Removes a security boundary assignment.
    """
    ...

4. platform_app/forms.py
Since DRF serializers are banned, we use Django Forms for strict request payload validation.
from django import forms
from platform_app.models import Node

class CreateNodeForm(forms.Form):
    """Validates the JSON payload for Node instantiation."""
    parent_node_id = forms.UUIDField(required=False)
    node_type = forms.ChoiceField(choices=Node.NodeType.choices, required=True)
    node_name = forms.CharField(max_length=255, required=True)
    status = forms.ChoiceField(choices=Node.NodeStatus.choices, required=False)

class NodeSettingForm(forms.Form):
    """Validates Key-Value setting inputs."""
    setting_key = forms.CharField(max_length=100, required=True)
    setting_value = forms.JSONField(required=True)
    is_override = forms.BooleanField(required=False, initial=False)

class NodeAccessForm(forms.Form):
    """Validates security assignment parameters."""
    user_id = forms.UUIDField(required=True)
    role = forms.CharField(max_length=100, required=True)
    cascade_access = forms.BooleanField(required=False, initial=True)

5. platform_app/views.py
The "Thin Views". These act purely as traffic controllers: parsing HTTP, calling Forms, invoking Selectors/Services, and returning HTTP standard JsonResponse.
import json
from django.http import JsonResponse, HttpRequest
from django.views import View
from core.utils import build_error_response
from platform_app.forms import CreateNodeForm, NodeSettingForm
from platform_app.services import create_node, set_node_setting
from platform_app.selectors import get_node_descendants, resolve_node_setting
from core.exceptions import HierarchicalIntegrityError

class NodeRegistryView(View):
    """Handles POST for creation and GET for listing the enterprise structure."""
    
    def post(self, request: HttpRequest) -> JsonResponse:
        ...
        
    def get(self, request: HttpRequest) -> JsonResponse:
        ...


class NodeSettingsView(View):
    """Handles configuration of inheritance logic."""
    
    def post(self, request: HttpRequest, node_id: str) -> JsonResponse:
        ...

    def get(self, request: HttpRequest, node_id: str) -> JsonResponse:
        ...


class NodeHierarchyView(View):
    """Handles spatial traversal endpoints (fetching children/descendants)."""
    
    def get(self, request: HttpRequest, node_id: str) -> JsonResponse:
        ...

6. platform_app/tasks.py
While platform_app doesn't have heavy periodic workloads like financial rollovers, we define the signature file for future-proofing (e.g., massive node relocations that might need async tree recalculation).
from celery import shared_task
from uuid import UUID

@shared_task
def async_recalculate_ltree_paths(root_node_id: UUID) -> None:
    """
    Background worker task in the event a massive multi-level site restructuring 
    requires deferred processing to prevent HTTP timeouts.
    """
    ...


Architectural Review
Thin Views, Fat Services Enforced: The views.py has no if/else business rules and no Model.objects.create(). It strictly relies on the service bounds.
Database Synergy: The DDL rules (Ltree, UniqueConstraint for the Root Node, uq_user_node_role) are accurately ported to models.py to prevent any app-layer race conditions.
No DRF Used: We leverage django.forms.Form and django.http.JsonResponse.
Next Step:
Now that the Global Infrastructure (The "Where") is modeled, the foundation is set. Shall we move on to Master Data Management (mdm), which represents the "What" and the "Who" living within these nodes?

As the Principal Software Architect, I will now define the mdm (Master Data Management) app.
In our modular monolith, mdm defines the "Who" (Business Partners) and the "What" (Items). Following the Hub and Spoke pattern from the blueprint, Global definitions live universally, while Local execution rules exist as Node Extensions.
We will strictly enforce cross-app boundaries by importing the Node model from platform_app purely for Foreign Keys. The heavy read volume of MDM will be mitigated via caching and the database-level vw_effective_item_status view.
Here is the strict architectural blueprint for the mdm app.
1. mdm/models.py
This file defines the core master data entities and their extensions. We also map the PostgreSQL view vw_effective_item_status into a read-only unmanaged model to allow safe ORM queries against the conflict-resolution engine.
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
    traceability_type = models.CharField(max_length=20, choices=TraceabilityType.choices, default=TraceabilityType.NONE)
    global_status = models.CharField(max_length=30, choices=GlobalStatus.choices, default=GlobalStatus.IN_DEVELOPMENT)

    class Meta:
        db_table = 'mdm\".\"items'
        indexes = [
            models.Index(fields=['global_status'], name='idx_items_status'),
            models.Index(fields=['item_class'], name='idx_items_class'),
        ]


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
    local_status = models.CharField(max_length=30, choices=LocalStatus.choices, default=LocalStatus.ACTIVE)
    costing_method = models.CharField(max_length=30, choices=CostingMethod.choices)
    replenishment_rule = models.CharField(max_length=30, choices=ReplenishmentRule.choices)

    class Meta:
        db_table = 'mdm\".\"item_node_extensions'
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
        db_table = 'mdm\".\"vw_effective_item_status'


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
        db_table = 'mdm\".\"business_partners'


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
        db_table = 'mdm\".\"bp_node_roles'
        constraints = [
            UniqueConstraint(fields=['bp', 'node', 'bp_role'], name='uq_bp_node_role')
        ]

2. mdm/selectors.py
These functions strictly handle database reads. They encapsulate logic for utilizing Redis caching on Global entities, and querying the unmanaged DB View for local authorization checks.
from typing import Optional
from uuid import UUID
from django.db.models import QuerySet
from mdm.models import Item, ItemNodeExtension, BusinessPartner, BPNodeRole, EffectiveItemStatusView

def get_global_item(item_id: UUID) -> Optional[Item]:
    """
    Fetches the Global Item definition.
    Architectural Pattern: Attempts Redis Cache hit first -> Falls back to DB.
    """
    ...

def is_item_active_at_node(item_id: UUID, node_id: UUID) -> bool:
    """
    Extension Prerequisite check. Queries the EffectiveItemStatusView (managed=False)
    to see if effective_status == 'ACTIVE'. This prevents N+1 and evaluates the 
    Global vs Local conflict matrix instantly.
    """
    ...

def get_business_partner_hierarchy(bp_id: UUID) -> QuerySet[BusinessPartner]:
    """
    Fetches the BP and all its subsidiaries.
    """
    ...

def get_authorized_carriers_for_node(node_id: UUID) -> QuerySet[BPNodeRole]:
    """
    Reads BPNodeRoles filtering by 'CARRIER' and validating against the Node.
    """
    ...

3. mdm/services.py
Strictly state-changing logic. Enforces immutability laws and executes Row-Level Locks when creating/modifying Node Extensions to avoid race conditions.
from uuid import UUID
from mdm.models import Item, ItemNodeExtension, BusinessPartner, BPNodeRole

def create_global_item(sku: str, item_class: str, base_uom: str, description: str, traceability: str) -> Item:
    """
    Instantiates a Global Item.
    Fires celery task to hydrate Redis MDM Cache.
    """
    ...

def extend_item_to_node(
    item_id: UUID, 
    node_id: UUID, 
    costing_method: str, 
    replenishment_rule: str
) -> ItemNodeExtension:
    """
    Localizes an item to a Node.
    Uses 'select_for_update()' on the Item to prevent concurrent "Phantom Reads"
    from procurement/sales modules while the extension is being established.
    """
    ...

def update_base_uom(item_id: UUID, new_uom: str) -> Item:
    """
    Attempts to update Base UoM.
    Will implicitly hit DB Trigger 'trg_items_protect_uom'. If the item is ACTIVE 
    and transacted, PostgreSQL raises an IntegrityError. Service translates this 
    to a BusinessRuleViolation exception.
    """
    ...

def create_business_partner(bp_number: str, legal_name: str, parent_bp_id: UUID = None) -> BusinessPartner:
    """
    Instantiates a Universal BP.
    DB Trigger 'trg_bp_prevent_loops' guards against circular hierarchy.
    """
    ...

def assign_bp_role_to_node(bp_id: UUID, node_id: UUID, role: str, financial_terms: str) -> BPNodeRole:
    """
    Assigns a BP as a Supplier, Customer, etc., to a specific spatial Node.
    """
    ...

4. mdm/forms.py
Standard Django Forms to validate input payloads, strictly replacing DRF serializers.
from django import forms
from mdm.models import Item, ItemNodeExtension, BPNodeRole

class CreateItemForm(forms.Form):
    sku = forms.CharField(max_length=100, required=True)
    item_class = forms.ChoiceField(choices=Item.ItemClass.choices, required=True)
    base_uom = forms.CharField(max_length=20, required=True)
    global_description = forms.CharField(required=True)
    traceability_type = forms.ChoiceField(choices=Item.TraceabilityType.choices, required=False)

class ExtendItemForm(forms.Form):
    node_id = forms.UUIDField(required=True)
    costing_method = forms.ChoiceField(choices=ItemNodeExtension.CostingMethod.choices, required=True)
    replenishment_rule = forms.ChoiceField(choices=ItemNodeExtension.ReplenishmentRule.choices, required=True)

class BPRoleForm(forms.Form):
    bp_id = forms.UUIDField(required=True)
    node_id = forms.UUIDField(required=True)
    bp_role = forms.ChoiceField(choices=BPNodeRole.BPRole.choices, required=True)
    financial_terms = forms.CharField(max_length=50, required=True)

5. mdm/views.py
The "Thin Views". Parses HTTP, delegates to forms, invokes services/selectors, and returns JSON.
from django.http import JsonResponse, HttpRequest
from django.views import View
from core.utils import build_error_response
from mdm.forms import CreateItemForm, ExtendItemForm, BPRoleForm
from mdm.services import create_global_item, extend_item_to_node, assign_bp_role_to_node
from mdm.selectors import get_global_item, is_item_active_at_node

class ItemRegistryView(View):
    """Handles GET/POST for Universal Items."""
    
    def post(self, request: HttpRequest) -> JsonResponse:
        ...

    def get(self, request: HttpRequest, item_id: str) -> JsonResponse:
        ...


class ItemNodeExtensionView(View):
    """Handles GET/POST for Local Item Extensions."""
    
    def post(self, request: HttpRequest, item_id: str) -> JsonResponse:
        ...

    def get(self, request: HttpRequest, item_id: str, node_id: str) -> JsonResponse:
        ...


class BusinessPartnerRoleView(View):
    """Handles assignment of BPs to specific nodes."""
    
    def post(self, request: HttpRequest) -> JsonResponse:
        ...

6. mdm/tasks.py
MDM defines the global cache strategies to protect database latency. Since Items and BPs rarely undergo core structural changes once approved, we cache the Global layers in Redis.
from celery import shared_task
from uuid import UUID

@shared_task
def invalidate_mdm_cache(entity_type: str, entity_id: UUID) -> None:
    """
    Listens for updates from mdm.services and actively invalidates Redis keys 
    for Items or Business Partners, forcing the next selector read to fetch from DB.
    """
    ...

@shared_task
def warm_item_cache(item_id: UUID) -> None:
    """
    Hydrates the Redis cache immediately after a new item is created or updated.
    """
    ...


Architectural Review
Dimensional Independence: The separation of Item and ItemNodeExtension respects the "Hub and Spoke" pattern, and using the EffectiveItemStatusView safely offloads the conflict logic to PostgreSQL.
Cache Strategy Established: selectors.py and tasks.py outline the boundaries for the Redis Cloud Memorystore architecture dictated by the blueprint.
No Database Drift: Base UoM immutability and Acyclic BP hierarchies are firmly anchored to the underlying DB triggers via domain exceptions in services.py.
Next Step:
Now that we have established Where things happen (platform_app) and What is involved (mdm), we must define the instructions to make them. Shall we move on to engineering (Product Lifecycle), which defines the BOMs, Routings, and Engineering Change Orders (ECOs)?

As the Principal Software Architect, I will now define the engineering app (Product Lifecycle & Engineering).
In our modular monolith, engineering is the "Recipe" layer. It defines how an Item from MDM is physically assembled at a Node from the Platform. This module is incredibly sensitive to mathematical loops (BOM explosions) and race conditions during production changes. We will map PostgreSQL's native daterange fields for temporal effectivity and enforce the ECO (Engineering Change Order) locking mechanism strictly through Celery.
Here is the strict architectural blueprint for the engineering app.
1. engineering/models.py
This file maps the Manufacturing Triad (BOM Header, BOM Lines, Routings) and the Governance engine (ECO). We explicitly import Item from mdm and Node from platform_app to establish cross-boundary Foreign Keys.
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
        db_table = 'eng\".\"bom_headers'
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
    effectivity_dates = DateRangeField(default=list)  # PostgreSQL native daterange

    class Meta:
        db_table = 'eng\".\"bom_lines'
        indexes = [
            models.Index(fields=['component_item'], name='idx_bom_lines_component'),
            # Note: GiST index for effectivity_dates is managed via raw SQL / migrations
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
        db_table = 'eng\".\"routings'
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
        db_table = 'eng\".\"ecos'

2. engineering/selectors.py
Reads from the Engineering module must be highly optimized to support MES Work Order generation. We encapsulate hierarchical inheritance lookups here.
from typing import Optional, List
from uuid import UUID
from django.db.models import QuerySet
from engineering.models import BOMHeader, BOMLine, Routing

def get_active_bom_for_node(item_id: UUID, node_id: UUID) -> Optional[BOMHeader]:
    """
    Node-Based Resolution (Logical Inheritance).
    If a Work Order is created at "Site A", this selector searches for an ACTIVE BOM 
    tied to "Site A". If none exists, it leverages the platform ltree path to traverse 
    upward to find a Regional or Global BOM.
    """
    ...

def get_bom_explosion(bom_id: UUID, effective_date: str) -> List[BOMLine]:
    """
    Retrieves the active ingredients for a given date. 
    Filters the PostgreSQL daterange using the @> (contains) operator to ensure 
    only components valid for the target execution date are returned.
    Also blows through any 'PHANTOM' sub-assemblies.
    """
    ...

def get_routing_sequence(bom_id: UUID) -> QuerySet[Routing]:
    """
    Fetches the sequential manufacturing steps for MES execution.
    """
    ...

3. engineering/services.py
Strictly state-changing logic. This layer implicitly interacts with the PostgreSQL triggers protecting against Acyclic BOM loops and Immutability locks.
from uuid import UUID
from datetime import date
from decimal import Decimal
from engineering.models import BOMHeader, BOMLine, Routing, EngineeringChangeOrder

def create_draft_bom(item_id: UUID, node_id: UUID, bom_type: str, revision_level: str) -> BOMHeader:
    """
    Instantiates a new DRAFT BOM. 
    """
    ...

def add_bom_line(bom_id: UUID, component_item_id: UUID, quantity: Decimal, scrap_factor: Decimal, valid_from: date, valid_to: date) -> BOMLine:
    """
    Adds a component to a BOM.
    DB Trigger 'trg_bom_lines_prevent_loops' acts as a strict safeguard here. If an 
    IntegrityError is thrown by the trigger, this service catches it and raises a
    custom HierarchicalIntegrityError to the user.
    """
    ...

def draft_eco(target_bom_id: UUID, node_id: UUID, reason_code: str) -> EngineeringChangeOrder:
    """
    Generates a new ECO for governance review.
    """
    ...

def approve_eco(eco_id: UUID, effectivity_date: date, approved_by_user_id: UUID) -> EngineeringChangeOrder:
    """
    Transitions ECO to APPROVED and sets the strict effectivity transition date.
    """
    ...

4. engineering/forms.py
Standard Django Forms to validate request payloads, replacing DRF. Date ranges are handled explicitly to pass into PostgreSQL cleanly.
from django import forms
from engineering.models import BOMHeader, EngineeringChangeOrder

class DraftBOMForm(forms.Form):
    item_id = forms.UUIDField(required=True)
    node_id = forms.UUIDField(required=True)
    bom_type = forms.ChoiceField(choices=BOMHeader.BOMType.choices, required=True)
    revision_level = forms.CharField(max_length=50, required=True)

class BOMLineForm(forms.Form):
    component_item_id = forms.UUIDField(required=True)
    quantity = forms.DecimalField(max_digits=19, decimal_places=4, required=True)
    scrap_factor = forms.DecimalField(max_digits=5, decimal_places=4, required=False, initial=0.0)
    valid_from = forms.DateField(required=True)
    valid_to = forms.DateField(required=False)  # Maps to upper bound of PostgreSQL daterange

class RoutingForm(forms.Form):
    operation_seq = forms.IntegerField(min_value=1, required=True)
    work_center_id = forms.UUIDField(required=True)
    standard_time = forms.DecimalField(max_digits=19, decimal_places=4, required=True)

class ECOApprovalForm(forms.Form):
    effectivity_date = forms.DateTimeField(required=True)

5. engineering/views.py
The "Thin Views". Handles HTTP requests, invokes forms, calls services, and formats JSON responses.
from django.http import JsonResponse, HttpRequest
from django.views import View
from core.utils import build_error_response
from engineering.forms import DraftBOMForm, BOMLineForm, RoutingForm, ECOApprovalForm
from engineering.services import create_draft_bom, add_bom_line, approve_eco
from engineering.selectors import get_bom_explosion
from engineering.tasks import execute_eco_transition

class BOMRegistryView(View):
    """Handles POST for creation of Master Recipes."""
    
    def post(self, request: HttpRequest) -> JsonResponse:
        ...

class BOMLineView(View):
    """Handles adding components and retrieving the BOM Explosion."""
    
    def post(self, request: HttpRequest, bom_id: str) -> JsonResponse:
        ...

    def get(self, request: HttpRequest, bom_id: str) -> JsonResponse:
        ...

class ECOExecutionView(View):
    """
    Handles the execution of an Approved ECO.
    As per Architectural Directives, this endpoint DOES NOT process synchronously.
    """
    
    def post(self, request: HttpRequest, eco_id: str) -> JsonResponse:
        # Validate ECO exists and is APPROVED...
        # Fire and forget async Celery worker
        execute_eco_transition.delay(eco_id)
        
        return JsonResponse({"status": "ECO Execution Queued"}, status=202)

6. engineering/tasks.py
Crucial for engineering. In enterprise systems, flipping an ECO to ACTIVE invalidates the previous revision. This forces standard cost recalculations, MRP regeneration, and sweeps through downstream tables. It must be asynchronous.
from celery import shared_task
from uuid import UUID

@shared_task(bind=True)
def execute_eco_transition(self, eco_id: UUID) -> None:
    """
    The background engine for "Strict Effectivity Handoffs".
    
    1. Locks the ECO row.
    2. Identifies the active Old Revision of the target item/node.
    3. Changes Old Revision status -> 'OBSOLETE'.
    4. Changes Target BOM status -> 'ACTIVE'.
    5. Changes ECO status -> 'EXECUTED'.
    6. Fires event to recalculate Standard Costing in Finance/MES.
    
    Wrapped entirely in transaction.atomic() to ensure atomic handoff.
    """
    ...


Architectural Review
Database Triggers vs Application State: The pure database-level Acyclic BOM constraint (from the blueprint) ensures that even bulk data imports cannot create infinite recursive loops. The services.py catches these DB errors cleanly.
Temporal Overlapping (dateranges): Using DateRangeField respects PostgreSQL's native capability to handle component effectivity seamlessly, avoiding complex if start_date <= X <= end_date logic in Django.
Async Governance (Celery): The ECOExecutionView strictly offloads execution to tasks.py, conforming exactly to the Cloud Architect Directive: Do not process this synchronously rule from the blueprint.
Next Step:
Now that we have the "Recipe" modeled, we are ready to move to the shop floor where these recipes become physical realities. Shall we move on to the Manufacturing Execution System (mes), which governs Work Orders, capacity logic, and concurrency-heavy operator scanner logs?

As the Principal Software Architect, I will now define the mes (Manufacturing Execution System) app.
In our modular monolith, mes represents the "Making" layer. This module operates on the shop floor where hundreds of barcode scanners and PLCs constantly ping the API to log yield, scrap, and material consumption.
To prevent catastrophic database deadlocks and race conditions (lost updates) under this heavy concurrency, we will strictly enforce PostgreSQL row-level locking (select_for_update()) in the service layer, and we will decouple financial cost rollups into asynchronous Celery tasks to ensure API responses remain sub-100ms.
Here is the strict architectural blueprint for the mes app.
1. mes/models.py
This file maps the transactional execution tickets (Work Orders) and the immutable ledger of shop floor events (Production Transactions).
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
        db_table = 'mes\".\"work_centers'


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
        db_table = 'mes\".\"work_orders'
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
        db_table = 'mes\".\"wo_operations'
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
        db_table = 'mes\".\"wo_material_requirements'
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
        db_table = 'mes\".\"production_transactions'
        indexes = [
            models.Index(fields=['batch_serial_ref'], name='idx_pt_batch'),
        ]

2. mes/selectors.py
Query abstractions. These provide safe read access to the state of production without initiating DB locks.
from uuid import UUID
from typing import Optional
from django.db.models import QuerySet
from mes.models import WorkOrder, WOOperation, WOMaterialRequirement

def get_work_order_details(wo_id: UUID) -> Optional[WorkOrder]:
    """Fetches WO with pre-fetched operations and material requirements."""
    ...

def get_pending_materials_for_wo(wo_id: UUID) -> QuerySet[WOMaterialRequirement]:
    """Returns materials where consumed_qty < required_qty."""
    ...

def get_work_center_load(work_center_node_id: UUID) -> QuerySet[WOOperation]:
    """Returns active operations currently queued or in-progress at a Work Center."""
    ...

3. mes/services.py
This is where the architectural mandates are executed. We strictly enforce concurrency control using select_for_update() to prevent lost updates when operators scan items simultaneously.
from uuid import UUID
from decimal import Decimal
from django.db import transaction
from mes.models import WorkOrder, WOMaterialRequirement, WOOperation, ProductionTransaction
from core.exceptions import ResourceLockedException, BusinessRuleViolation

def create_and_release_work_order(item_id: UUID, node_id: UUID, target_qty: Decimal) -> WorkOrder:
    """
    The Snapshot Principle.
    1. Calls engineering.selectors.get_active_bom_for_node()
    2. Calls engineering.selectors.get_routing_sequence()
    3. Generates WO, copies BOM to WOMaterialRequirement, Routings to WOOperation.
    4. Transitions to 'RELEASED'.
    """
    ...

@transaction.atomic
def log_material_issue(wo_id: UUID, component_item_id: UUID, work_center_id: UUID, scanned_qty: Decimal, batch_ref: str, operator_id: UUID) -> ProductionTransaction:
    """
    Mandatory Concurrency Pattern (Blueprint Section 5).
    Safely increments consumption under heavy load.
    """
    try:
        # 1. Thread-safe row lock. Blocks other scanner threads until transaction completes.
        req = WOMaterialRequirement.objects.select_for_update(nowait=False).get(
            wo_id=wo_id, component_item_id=component_item_id
        )
    except WOMaterialRequirement.DoesNotExist:
        raise BusinessRuleViolation("Component is not required for this Work Order.")

    # 2. Increment safely in memory
    req.consumed_qty += scanned_qty
    req.save()

    # 3. Log the immutable transaction for genealogy/traceability
    pt = ProductionTransaction.objects.create(
        wo_id=wo_id,
        work_center_id=work_center_id,
        event_type=ProductionTransaction.EventType.MATERIAL_ISSUE,
        quantity=scanned_qty,
        batch_serial_ref=batch_ref,
        operator_id=operator_id
    )

    # 4. Trigger async cost rollup
    from mes.tasks import execute_cost_rollup
    execute_cost_rollup.delay(wo_id=wo_id, transaction_id=pt.transaction_id)

    return pt

@transaction.atomic
def log_yield(wo_op_id: UUID, yield_qty: Decimal, operator_id: UUID) -> ProductionTransaction:
    """
    Logs good parts produced.
    DB Trigger 'trg_enforce_operation_sequence' will fire here to prevent Yield on Op 20 
    if Op 10 hasn't produced enough yet. Catches IntegrityError -> BusinessRuleViolation.
    """
    ...

def complete_work_order(wo_id: UUID) -> WorkOrder:
    """
    Attempts to close WO.
    DB Trigger 'trg_enforce_material_allocation' guarantees completion fails 
    if consumed < required.
    """
    ...

4. mes/forms.py
Replaces DRF for validating barcode scanner payloads and UI inputs.
from django import forms

class CreateWorkOrderForm(forms.Form):
    item_id = forms.UUIDField(required=True)
    node_id = forms.UUIDField(required=True)
    target_quantity = forms.DecimalField(max_digits=19, decimal_places=4, min_value=0.0001, required=True)

class MaterialIssueForm(forms.Form):
    component_item_id = forms.UUIDField(required=True)
    work_center_id = forms.UUIDField(required=True)
    scanned_qty = forms.DecimalField(max_digits=19, decimal_places=4, min_value=0.0001, required=True)
    batch_serial_ref = forms.CharField(max_length=100, required=True) # Traceability mandate

class OperationYieldForm(forms.Form):
    yield_qty = forms.DecimalField(max_digits=19, decimal_places=4, min_value=0.0001, required=True)
    work_center_id = forms.UUIDField(required=True)

5. mes/views.py
Extremely thin traffic controllers. They must respond to the physical shop floor rapidly.
from django.http import JsonResponse, HttpRequest
from django.views import View
from mes.forms import CreateWorkOrderForm, MaterialIssueForm, OperationYieldForm
from mes.services import create_and_release_work_order, log_material_issue, log_yield
from core.exceptions import BusinessRuleViolation

class WorkOrderAPIView(View):
    def post(self, request: HttpRequest) -> JsonResponse:
        ...

class MaterialIssueAPIView(View):
    """Highly concurrent endpoint for RF Scanners."""
    def post(self, request: HttpRequest, wo_id: str) -> JsonResponse:
        form = MaterialIssueForm(json.loads(request.body))
        if not form.is_valid():
            return JsonResponse(form.errors, status=400)
            
        try:
            pt = log_material_issue(
                wo_id=wo_id,
                component_item_id=form.cleaned_data['component_item_id'],
                work_center_id=form.cleaned_data['work_center_id'],
                scanned_qty=form.cleaned_data['scanned_qty'],
                batch_ref=form.cleaned_data['batch_serial_ref'],
                operator_id=request.user.id
            )
            # Returns 201 immediately; Cost rollup happens in the background.
            return JsonResponse({"transaction_id": str(pt.transaction_id), "status": "Logged"}, status=201)
        except BusinessRuleViolation as e:
            return JsonResponse({"error": str(e)}, status=409)

class OperationYieldAPIView(View):
    def post(self, request: HttpRequest, wo_op_id: str) -> JsonResponse:
        ...

6. mes/tasks.py
The async boundary protecting database CPU. When a scanner logs material or labor, we do not perform synchronous multi-table joins to standard costs. This Celery worker takes the queue.
from celery import shared_task
from uuid import UUID
from django.db import transaction

@shared_task(bind=True, max_retries=3)
def execute_cost_rollup(self, wo_id: UUID, transaction_id: UUID) -> None:
    """
    Cost Rollup Execution (Blueprint Section 5).
    1. Fetches the ProductionTransaction.
    2. If Labor: Multiplies labor_hours by WorkCenter.standard_cost_rate.
    3. If Material: Queries mdm.item_node_extensions for component standard cost.
    4. Applies an atomic increment to WorkOrder.actual_cost.
    """
    ...


Architectural Review
Thread-Safe Consistency: The log_material_issue service implements a strict select_for_update() lock. This guarantees that if two PLCs attempt to deduct material at the exact same millisecond, the database serializes the writes, preventing a phantom read.
Traceability Mandate: The MaterialIssueForm requires batch_serial_ref. This provides the unbroken genealogy link from Raw Material to Finished Good.
Delegation of Heavy Math: execute_cost_rollup lives in tasks.py. The views.py returns 201 Created immediately to the scanner, while Celery updates the financial values, preventing HTTP timeouts on the shop floor.
Next Step:
Now that we are making things (mes), we must be able to physically store, move, and allocate them with absolute spatial precision. Shall we move on to Supply Chain & Warehouse (wms), the most concurrency-heavy application in the entire ERP?

As the Principal Software Architect, I will now define the wms (Supply Chain & Warehouse Management System) app.
This is the most concurrency-heavy application in the entire ERP. Hundreds of RF barcode scanners will hit this module simultaneously. To survive this, we must strictly implement SELECT FOR UPDATE SKIP LOCKED in the Allocation Engine, enforce database-level Zero-Negative constraints, and treat Handling Units (LPNs) as Mobile Nodes to eliminate mass-update bottlenecks during physical movements.
Here is the strict architectural blueprint for the wms app.
1. wms/models.py
This maps the physical layout and inventory realities. Note the Unmanaged model for the Allocation View, which mathematically hides QA_HOLD inventory without complex Python logic.
import uuid
from django.db import models
from django.db.models import UniqueConstraint
from core.models import TimeStampedModel
from platform_app.models import Node
from mdm.models import Item


class LPN(models.Model):
    """
    License Plate Number (Handling Unit).
    Architectural Brilliance: LPNs are "Mobile Nodes". By extending the Node model,
    moving a pallet with 50 items only requires ONE database update 
    (changing the LPN Node's parent_node_id to the new Aisle/Bin).
    """
    class ContainerType(models.TextChoices):
        PALLET = 'PALLET', 'Pallet'
        TOTE = 'TOTE', 'Tote'
        PARCEL = 'PARCEL', 'Parcel'
        GAYLORD = 'GAYLORD', 'Gaylord'

    node = models.OneToOneField(Node, primary_key=True, on_delete=models.CASCADE, related_name='lpn_profile')
    parent_lpn = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='nested_lpns')
    container_type = models.CharField(max_length=50, choices=ContainerType.choices)
    max_weight = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    max_volume = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    class Meta:
        db_table = 'wms\".\"lpns'


class InventoryPosition(TimeStampedModel):
    """
    The Ledger of Reality.
    A discrete quantum of stock at a specific location (Bin or LPN) at a specific time.
    """
    class StockStatus(models.TextChoices):
        AVAILABLE = 'AVAILABLE', 'Available'
        ALLOCATED = 'ALLOCATED', 'Allocated'
        QA_HOLD = 'QA_HOLD', 'QA Hold'
        BLOCKED = 'BLOCKED', 'Blocked'

    position_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    node = models.ForeignKey(Node, on_delete=models.RESTRICT, related_name='inventory_positions')
    item = models.ForeignKey(Item, on_delete=models.RESTRICT, related_name='inventory_positions')
    batch_serial_id = models.CharField(max_length=100, null=True, blank=True)
    quantity = models.DecimalField(max_digits=19, decimal_places=4, default=0.0000)
    stock_status = models.CharField(max_length=30, choices=StockStatus.choices, default=StockStatus.AVAILABLE)
    last_counted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'wms\".\"inventory_positions'
        indexes = [
            models.Index(fields=['node'], name='idx_inv_node'),
            models.Index(fields=['batch_serial_id'], name='idx_inv_batch'),
        ]
        # Blueprint Note: The DB physically enforces quantity >= 0 via CHECK constraint.


class AllocatableInventoryView(models.Model):
    """
    Unmanaged View mapping to wms.vw_allocatable_inventory.
    Automatically filters out QA_HOLD/BLOCKED and zero-qty positions.
    Includes the 'lineage_path' from the Global Node for lightning-fast spatial querying.
    """
    position_id = models.UUIDField(primary_key=True)
    node_id = models.UUIDField()
    item_id = models.UUIDField()
    batch_serial_id = models.CharField(max_length=100)
    quantity = models.DecimalField(max_digits=19, decimal_places=4)
    lineage_path = models.TextField()  # Mapped from ltree

    class Meta:
        managed = False
        db_table = 'wms\".\"vw_allocatable_inventory'


class WarehouseTask(TimeStampedModel):
    """
    The Work Queue.
    Directives to physically move inventory from Node A to Node B.
    """
    class TaskType(models.TextChoices):
        PUTAWAY = 'PUTAWAY', 'Putaway'
        PICK = 'PICK', 'Pick'
        REPLENISHMENT = 'REPLENISHMENT', 'Replenishment'
        CYCLE_COUNT = 'CYCLE_COUNT', 'Cycle Count'
        TRANSFER = 'TRANSFER', 'Transfer'

    class TaskStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
        COMPLETED = 'COMPLETED', 'Completed'
        CANCELLED = 'CANCELLED', 'Cancelled'
        EXCEPTION = 'EXCEPTION', 'Exception'

    task_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_node = models.ForeignKey(Node, on_delete=models.RESTRICT, related_name='outbound_tasks')
    target_node = models.ForeignKey(Node, on_delete=models.RESTRICT, related_name='inbound_tasks')
    item = models.ForeignKey(Item, on_delete=models.RESTRICT, null=True, blank=True)
    lpn = models.ForeignKey(LPN, on_delete=models.RESTRICT, null=True, blank=True)
    task_qty = models.DecimalField(max_digits=19, decimal_places=4, null=True, blank=True)
    task_type = models.CharField(max_length=30, choices=TaskType.choices)
    status = models.CharField(max_length=30, choices=TaskStatus.choices, default=TaskStatus.PENDING)
    assigned_user_id = models.UUIDField(null=True, blank=True) # System Auth User ID
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'wms\".\"warehouse_tasks'
        indexes = [
            models.Index(fields=['status', 'task_type'], name='idx_tasks_queue'),
        ]

2. wms/selectors.py
Query abstractions ensuring we never read from base tables for availability, only from the mathematically safe View.
from typing import Optional
from uuid import UUID
from django.db.models import QuerySet
from wms.models import WarehouseTask, AllocatableInventoryView, InventoryPosition

def get_next_worker_task(user_id: UUID) -> Optional[WarehouseTask]:
    """Fetches the next highest priority PENDING task in the user's assigned Zone."""
    ...

def get_inventory_in_node_tree(node_id: UUID, item_id: UUID) -> QuerySet[AllocatableInventoryView]:
    """
    Leverages the ltree 'lineage_path' in the View to find all allocatable inventory
    within a warehouse, zone, or specific aisle using PostgreSQL '@>' operator.
    """
    ...

3. wms/services.py
The "Fat Services". This enforces the crucial SKIP LOCKED allocation pattern and cross-app architectural boundaries.
from uuid import UUID
from decimal import Decimal
from django.db import transaction
from wms.models import InventoryPosition, LPN, WarehouseTask, AllocatableInventoryView
from platform_app.services import update_node_parent
from procurement.services import receive_po_line  # Cross-app strict boundary
from core.exceptions import BusinessRuleViolation, ResourceLockedException

@transaction.atomic
def allocate_inventory(item_id: UUID, target_node_id: UUID, requested_qty: Decimal) -> list[WarehouseTask]:
    """
    Mandatory Concurrency Pattern (Blueprint Sec 5).
    Uses SKIP LOCKED to rapidly allocate inventory without bottlenecking parallel orders.
    """
    allocated_qty = Decimal('0.0000')
    tasks = []

    # 1. Fetch available positions, strictly ordered by FIFO, skipping rows locked by other threads
    available_positions = AllocatableInventoryView.objects.raw('''
        SELECT position_id, quantity, node_id 
        FROM wms.vw_allocatable_inventory
        WHERE item_id = %s
        ORDER BY batch_serial_id ASC
        FOR UPDATE SKIP LOCKED
    ''', [str(item_id)])

    for position in available_positions:
        if allocated_qty >= requested_qty:
            break
            
        qty_to_take = min(position.quantity, requested_qty - allocated_qty)
        
        # 2. Mutate actual base table to 'ALLOCATED' (or split the position row)
        base_pos = InventoryPosition.objects.get(pk=position.position_id)
        # ... logic to deduct qty and spawn an 'ALLOCATED' cloned row ...
        
        # 3. Generate Pick Task
        task = WarehouseTask.objects.create(
            source_node_id=base_pos.node_id,
            target_node_id=target_node_id,
            item_id=item_id,
            task_qty=qty_to_take,
            task_type=WarehouseTask.TaskType.PICK
        )
        tasks.append(task)
        allocated_qty += qty_to_take

    if allocated_qty < requested_qty:
        # DB rolls back entire transaction if we cannot fulfill the whole order
        raise BusinessRuleViolation(f"Insufficient allocatable inventory. Found {allocated_qty} of {requested_qty}")

    return tasks

def move_lpn(lpn_id: UUID, new_parent_node_id: UUID) -> LPN:
    """
    LPN as a Mobile Node (Blueprint Sec 5).
    Instead of iterating and updating 50 InventoryPositions, we make a single
    cross-app call to `platform_app.services` to change the LPN Node's parent.
    The DB trigger recalculates the spatial path for everything inside instantly.
    """
    update_node_parent(node_id=lpn_id, new_parent_node_id=new_parent_node_id)
    return LPN.objects.get(pk=lpn_id)

@transaction.atomic
def execute_goods_receipt(po_line_id: UUID, destination_node_id: UUID, qty: Decimal, batch_ref: str = None) -> InventoryPosition:
    """
    The WMS Goods Receipt API logic.
    We respect the Rule 3 boundary: We cannot update procurement.POLine directly.
    We call `procurement.services` to handle its own lock and over-receipt validation,
    then we physically create the inventory here.
    """
    # 1. Cross-app service call (Procurement handles the SELECT FOR UPDATE lock on the PO Line)
    receive_po_line(po_line_id=po_line_id, received_qty=qty)

    # 2. Create physical inventory
    # ... logic to fetch item_id from PO Line ...
    position = InventoryPosition.objects.create(
        node_id=destination_node_id,
        item_id=item_id,
        quantity=qty,
        batch_serial_id=batch_ref
    )
    
    # 3. Async Finance trigger is fired from Celery Tasks, not here.
    return position

4. wms/forms.py
Strictly typed Django Forms to validate input from RF Scanners.
from django import forms

class LPNMoveForm(forms.Form):
    lpn_id = forms.UUIDField(required=True)
    destination_node_id = forms.UUIDField(required=True)

class GoodsReceiptForm(forms.Form):
    po_line_id = forms.UUIDField(required=True)
    destination_node_id = forms.UUIDField(required=True)
    received_qty = forms.DecimalField(max_digits=19, decimal_places=4, min_value=0.0001, required=True)
    batch_serial_ref = forms.CharField(max_length=100, required=False)

class TaskExecutionForm(forms.Form):
    scanned_node_id = forms.UUIDField(required=True)
    scanned_item_id = forms.UUIDField(required=False)
    scanned_lpn_id = forms.UUIDField(required=False)
    picked_qty = forms.DecimalField(max_digits=19, decimal_places=4, required=True)

5. wms/views.py
Thin controllers tailored for high-speed scanner API responses.
import json
from django.http import JsonResponse, HttpRequest
from django.views import View
from wms.forms import GoodsReceiptForm, LPNMoveForm, TaskExecutionForm
from wms.services import execute_goods_receipt, move_lpn
from core.exceptions import BusinessRuleViolation, ResourceLockedException

class GoodsReceiptAPIView(View):
    """Scanner endpoint for inbound dock receiving."""
    def post(self, request: HttpRequest) -> JsonResponse:
        form = GoodsReceiptForm(json.loads(request.body))
        if not form.is_valid():
            return JsonResponse(form.errors, status=400)
            
        try:
            position = execute_goods_receipt(
                po_line_id=form.cleaned_data['po_line_id'],
                destination_node_id=form.cleaned_data['destination_node_id'],
                qty=form.cleaned_data['received_qty'],
                batch_ref=form.cleaned_data.get('batch_serial_ref')
            )
            
            # Broadcast event to Celery/Redis for decoupled listeners (QMS, Finance)
            from wms.tasks import broadcast_goods_receipt_event
            broadcast_goods_receipt_event.delay(str(position.position_id), str(form.cleaned_data['po_line_id']))
            
            return JsonResponse({"status": "Received", "position_id": str(position.position_id)}, status=201)
            
        except BusinessRuleViolation as e:
            return JsonResponse({"error": str(e)}, status=409)
        except ResourceLockedException:
            return JsonResponse({"error": "Resource is currently locked by another process."}, status=423)


class LPNMoveAPIView(View):
    """Scanner endpoint for forklift drivers moving pallets."""
    def post(self, request: HttpRequest) -> JsonResponse:
        form = LPNMoveForm(json.loads(request.body))
        if not form.is_valid():
            return JsonResponse(form.errors, status=400)
            
        lpn = move_lpn(form.cleaned_data['lpn_id'], form.cleaned_data['destination_node_id'])
        return JsonResponse({"status": "LPN Moved", "lpn_id": str(lpn.node_id)}, status=200)

6. wms/tasks.py
As dictated by the QMS blueprint section, WMS does not directly import QMS to put things on QA Hold. Instead, WMS broadcasts a completely decoupled event.
from celery import shared_task
from uuid import UUID

@shared_task
def broadcast_goods_receipt_event(position_id: str, po_line_id: str) -> None:
    """
    Pub/Sub implementation. 
    1. QMS listens to this to generate an InspectionOrder and veto the inventory status.
    2. Finance listens to this to post the GR/IR Subledger Journal Entry.
    WMS remains unaware of both, ensuring lightning-fast scanner responses.
    """
    # In practice, this could push to Redis Pub/Sub, Google Pub/Sub, or simply 
    # trigger the targeted Celery tasks in 'qms' and 'finance' directly.
    from qms.tasks import evaluate_inbound_inspection
    from finance.tasks import post_goods_receipt_subledger
    
    evaluate_inbound_inspection.delay(position_id)
    post_goods_receipt_subledger.delay(po_line_id)


Architectural Review
SKIP LOCKED Engine Enforced: The allocate_inventory service implements raw SQL to specifically leverage FOR UPDATE SKIP LOCKED. This guarantees high-volume E-Commerce or MES operations will not bottleneck each other while competing for the same bin of screws.
LPN as a Mobile Node: move_lpn perfectly implements the architectural directive: it changes the node parent via platform_app.services, letting PostgreSQL recalculate the ltree in microseconds.
Strict Application Boundaries: wms does not touch procurement.POLine directly. It calls the specific bounded receive_po_line service, maintaining pure domain isolation.
Next Step:
Now that we can build things (mes) and store/move them (wms), we must sell and monetize them. Shall we proceed to Commercial & Logistics (commercial), managing Order-to-Cash, the ATP engine, and Post Goods Issue (PGI) immutability?
******************************************************************************************************
Explanation
As the Principal Software Architect, I would be glad to break down wms/models.py.
In an enterprise ERP, the Warehouse Management System (WMS) is the Mathematical Ledger of Physical Reality. If the database says a pallet is in Aisle 4, but it is physically in Aisle 5, the entire factory can grind to a halt.
Therefore, wms/models.py is designed to rigidly enforce physical laws (you cannot have negative inventory) and optimize for speed.
Let’s go through this file step-by-step with a real-world warehouse example.

Step 1: The Cross-Boundary Imports
from platform_app.models import Node
from mdm.models import Item

The Concept: WMS does not define what a product is, nor does it define the layout of the building. It borrows them.
Node (from platform): Represents physical spaces (e.g., Dallas_Warehouse, Zone_A, Aisle_4, Bin_12).
Item (from mdm): Represents the abstract product (e.g., SKU-123: V8 Engine).
Real-World Example: WMS simply says: "I have 5 units of SKU-123 sitting inside Bin_12."

Step 2: The LPN (License Plate Number) Model
class LPN(models.Model):
    node = models.OneToOneField(Node, primary_key=True, on_delete=models.CASCADE)
    parent_lpn = models.ForeignKey('self', null=True, blank=True)
    container_type = models.CharField(choices=['PALLET', 'TOTE', 'PARCEL'])

The Concept: "LPN" is warehouse terminology for a movable container (a Pallet, a Tote, a Box) with a barcode on it.
The Architectural Brilliance (Mobile Nodes):
Notice that LPN has a OneToOneField linking exactly to a Node. In our system, a Pallet is just a physical location that can move.
Real-World Example:
Imagine a Pallet (LPN_Pallet_A) arrives at the Receiving Dock. Sitting on this pallet are 50 unique boxes of different items.
Standard ERP Design: If a forklift driver moves the pallet to Aisle_4, the database must execute an UPDATE statement on all 50 boxes to change their location to Aisle_4. This causes massive database locking and slowdowns.
Our DDD Design: Because LPN_Pallet_A is a Node, we just change the parent_node_id of LPN_Pallet_A from Receiving_Dock to Aisle_4. The PostgreSQL ltree extension instantly recalculates the spatial path for all 50 boxes in a fraction of a millisecond.

Step 3: The InventoryPosition Model
class InventoryPosition(TimeStampedModel):
    node = models.ForeignKey(Node, on_delete=models.RESTRICT)
    item = models.ForeignKey(Item, on_delete=models.RESTRICT)
    batch_serial_id = models.CharField(max_length=100, null=True, blank=True)
    quantity = models.DecimalField(max_digits=19, decimal_places=4)
    stock_status = models.CharField(choices=['AVAILABLE', 'ALLOCATED', 'QA_HOLD'])

The Concept: This is the core ledger. It represents a specific stack of goods at a specific location.
Real-World Example:
A worker scans 10 "V8 Engines" (Batch #999) and places them on LPN_Pallet_A. The database creates a row:
item = V8 Engine
node = LPN_Pallet_A
quantity = 10
batch_serial_id = #999
stock_status = AVAILABLE
Architectural Rule: The database DDL enforces CHECK (quantity >= 0). Even if two Django threads have a race condition and try to deduct 6 engines each (12 total), the PostgreSQL database will physically reject the second transaction, preventing the ERP from entering a mathematically impossible state (-2 engines).

Step 4: The AllocatableInventoryView (Unmanaged Model)
class AllocatableInventoryView(models.Model):
    position_id = models.UUIDField(primary_key=True)
    quantity = models.DecimalField()
    lineage_path = models.TextField()

    class Meta:
        managed = False
        db_table = 'wms"."vw_allocatable_inventory'

The Concept: managed = False means Django does not create this table. It points to a PostgreSQL View (a saved virtual query) we defined in the DDL blueprint.
Real-World Example:
Let's say a Quality Assurance (QMS) inspector finds a scratch on the 10 V8 Engines and changes their stock_status to QA_HOLD.
Meanwhile, the E-Commerce website asks the ERP: "Do we have any V8 Engines to sell to a customer?"
Instead of the Sales API needing to write complex logic (Inventory.objects.filter(quantity__gt=0).exclude(status='QA_HOLD')), it simply queries AllocatableInventoryView.objects.filter(item=V8_Engine).
Because the database View automatically filters out QA_HOLD, it instantly returns 0. The QA-held inventory is mathematically invisible to the sales engine. This is called Status-Based Isolation.

Step 5: The WarehouseTask Model
class WarehouseTask(TimeStampedModel):
    source_node = models.ForeignKey(Node, related_name='outbound_tasks')
    target_node = models.ForeignKey(Node, related_name='inbound_tasks')
    task_qty = models.DecimalField()
    task_type = models.CharField(choices=['PUTAWAY', 'PICK', 'CYCLE_COUNT'])
    status = models.CharField(choices=['PENDING', 'IN_PROGRESS', 'COMPLETED'])

The Concept: Inventory does not move magically. Every movement requires human or robotic labor. The WarehouseTask is the directive telling the worker what to do.
Real-World Example:
When the forklift driver picks up LPN_Pallet_A at the dock, the system generates a WarehouseTask:
task_type = PUTAWAY
source_node = Receiving_Dock
target_node = Aisle_4
lpn = LPN_Pallet_A
status = PENDING
The forklift driver looks at their scanner tablet. The Django API queries the WarehouseTask table and displays: "Drive to Receiving Dock, pick up Pallet A, and drop it in Aisle 4." Once they scan the barcode at Aisle 4, the API triggers the service to update the LPN's location and changes this task's status to COMPLETED.

Summary
By structuring wms/models.py this way, our Django backend doesn't have to do heavy lifting. It relies on the PostgreSQL database to manage spatial hierarchies (via Mobile LPN Nodes), block impossible math (zero-negative constraints), and hide bad inventory (Views).
Would you like to review how the wms/services.py safely allocates this inventory using the SKIP LOCKED concurrency pattern, or shall we move on to the next app?
That is a fantastic question, and it points to the exact "magic trick" of this architecture.
The confusion usually comes from looking for a field named lpn_id inside the InventoryPosition table. If you look at the model, that field doesn't exist!
So, how do we know what is inside the LPN?
The secret lies in the fact that an LPN is a Node.
Let me break down exactly how the database links the inventory to the pallet, step-by-step.
The Missing Link: node_id
Look at these two fields from the models:
In the LPN model: node = models.OneToOneField(Node, primary_key=True)
In the InventoryPosition model: node = models.ForeignKey(Node)
Because an LPN is a Node, the InventoryPosition simply points its node field directly to the LPN.
Step-by-Step Example: Putting an Engine on a Pallet
Let's walk through what happens in the database when a worker physically places 50 V8 Engines onto a brand new pallet.
1. The system creates the Pallet (LPN)
When the worker grabs an empty pallet and scans its barcode (let's call it PALLET-123), the system creates a new Node:
Node ID: uuid-0001
Node Type: LPN
Node Name: PALLET-123
Then, it creates the LPN record linked to that Node:
LPN ID (Node ID): uuid-0001
Container Type: PALLET
2. The system puts the inventory "inside" the Pallet
When the worker scans the 50 V8 Engines onto the pallet, the system creates an InventoryPosition.
To tell the database "these engines are on that pallet," we simply set the node field of the inventory to the LPN's Node ID:
Item: V8 Engine
Quantity: 50
Node ID: uuid-0001 (This is the Pallet!)
How do we ask the system "What is on this Pallet?"
If a manager walks up to PALLET-123 and scans it with their tablet, the Django backend executes a very simple query:
# 1. We look up the Pallet by its barcode
scanned_lpn = LPN.objects.get(node__node_name="PALLET-123")

# 2. We ask the Inventory Ledger: "Show me all inventory sitting at this Node"
contents = InventoryPosition.objects.filter(node=scanned_lpn.node)

for position in contents:
    print(f"Item: {position.item.sku}, Qty: {position.quantity}")

Output: Item: V8 Engine, Qty: 50
Why design it this way? (The Architectural Benefit)
You might ask: "Why not just add an lpn_id field to the Inventory table?"
Because of Mobility.
Imagine PALLET-123 currently sits on the Receiving Dock (Node uuid-dock).
The Pallet's parent is the Receiving Dock.
The Inventory's parent is the Pallet.
If a forklift driver moves the pallet from the Dock to Aisle 4 (Node uuid-aisle4), what happens to the inventory?
Nothing. We don't touch the InventoryPosition table at all. The 50 engines are still sitting on uuid-0001 (the Pallet). All we do is change the Pallet's parent from uuid-dock to uuid-aisle4.
Because of the PostgreSQL ltree spatial path, the database instantly knows that the Pallet—and all 50 engines sitting on it—are now mathematically inside Aisle 4.
Does this clarify how the inventory gets "inside" the LPN container?
This is a highly practical question. Let’s walk through the exact lifecycle of receiving a pallet and moving it into the warehouse. I will show you exactly what the database rows look like at each step.
At the end, I will specifically answer why the lpn Foreign Key exists on the WarehouseTask model.

Step 1: The Static Warehouse (Before the truck arrives)
First, the platform.nodes table holds the physical blueprint of our building. We have a Receiving Dock and an Aisle.
Table: platform.nodes
node_id
parent_node_id
node_type
node_name
lineage_path
Node-Dock
NULL
ZONE
Receiving Dock
Node-Dock
Node-Aisle1
NULL
ZONE
Aisle 1
Node-Aisle1

(Note: For readability, I am using simple strings like Node-Dock instead of real UUIDs).

Step 2: The Truck Arrives (Creating the LPN and Inventory)
A worker unloads a wooden pallet containing 50 V8 Engines. They stick a barcode on the pallet that reads PALLET-999.
The Django service does three things:
Creates a new Node for the Pallet.
Creates the LPN profile for that Node.
Creates the Inventory sitting on that Node.
Table: platform.nodes (Updated)
node_id
parent_node_id
node_type
node_name
lineage_path
Node-Pallet999
Node-Dock
LPN
PALLET-999
Node-Dock.Node-Pallet999

Table: wms.lpns
node_id (PK)
container_type
Node-Pallet999
PALLET

Table: wms.inventory_positions
position_id
node_id
item_id
quantity
stock_status
Pos-001
Node-Pallet999
V8-Engine
50
AVAILABLE

Look closely at the data: The 50 engines are sitting on Node-Pallet999. And Node-Pallet999 is currently sitting at Node-Dock.

Step 3: Generating the Move Instruction (The Warehouse Task)
The system now needs to tell a forklift driver to move this pallet from the Dock to Aisle 1. It creates a record in the WarehouseTask table.
Table: wms.warehouse_tasks
task_id
task_type
source_node_id
target_node_id
lpn_id
item_id
task_qty
Task-1
PUTAWAY
Node-Dock
Node-Aisle1
Node-Pallet999
NULL
NULL

Answer to your specific question: What is the purpose of the lpn_id FK here?
The WarehouseTask table supports two entirely different types of work:
Scenario A: Moving an entire Pallet (LPN Task)
If lpn_id is populated (like in the table above), it tells the worker: "Grab this entire Pallet and move it." Notice that item_id and task_qty are NULL. The worker doesn't need to count 50 engines. They just scan the PALLET-999 barcode, pick up the whole block of wood, and drive away.
Scenario B: Moving loose items (Loose Pick Task)
If a customer orders exactly 2 engines, the system creates a different task:
lpn_id = NULL
item_id = V8-Engine
task_qty = 2
This tells the worker: "Go to a location, pick up exactly 2 loose engines, and leave the rest behind."
By having the lpn_id FK, the API knows instantly whether to prompt the scanner for a container barcode or an item barcode.

Step 4: Executing the Task
The forklift driver picks up the pallet, drives to Aisle 1, scans the "Aisle 1" barcode on the wall, and clicks "Complete" on their scanner.
The Django API executes the move_lpn service. Watch what happens to the database.
Table: wms.inventory_positions (NO CHANGE!)
position_id
node_id
item_id
quantity
stock_status
Pos-001
Node-Pallet999
V8-Engine
50
AVAILABLE

Table: platform.nodes (UPDATED!)
node_id
parent_node_id
node_type
node_name
lineage_path
Node-Pallet999
Node-Aisle1
LPN
PALLET-999
Node-Aisle1.Node-Pallet999

The Architectural Result
We physically moved 50 items across a massive warehouse.
But because the inventory is tied to the LPN, and the LPN is a Node, we did not touch the inventory table. We simply updated ONE row in the platform.nodes table (changing the parent_node_id from the Dock to Aisle 1).
The PostgreSQL database automatically recalculated the lineage_path. If an executive runs a report asking "How many engines are in Aisle 1?", the database looks at the lineage_path, sees Node-Aisle1.Node-Pallet999, and instantly reports 50.
************************************************************************************************************

As the Principal Software Architect, I will now define the commercial (Commercial & Logistics) app.
In our modular monolith, this layer monetizes the inventory. It spans from the initial customer promise (Sales Order) to the physical dispatch (Shipment). Following the blueprint, we must enforce strict decoupling here: The API responding to customer checkouts cannot synchronously lock WMS inventory or trigger massive Subledger journal entries. We will implement the CQRS ATP Engine and the Asynchronous Post Goods Issue (PGI) boundaries.
Here is the strict architectural blueprint for the commercial app.
1. commercial/models.py
This file maps the Commercial Contract (Sales Order) and the Logistical Execution (Outbound Delivery & Shipment). We utilize standard Django models with db_table constraints linking to the physical com schema.
import uuid
from django.db import models
from django.db.models import UniqueConstraint
from core.models import TimeStampedModel
from platform_app.models import Node
from mdm.models import Item, BusinessPartner
from wms.models import LPN


class SalesOrder(TimeStampedModel):
    """
    The Commercial Contract.
    The binding agreement between the enterprise (Selling Node) and the Customer.
    """
    class OrderStatus(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        CONFIRMED = 'CONFIRMED', 'Confirmed'
        PROCESSING = 'PROCESSING', 'Processing'
        SHIPPED = 'SHIPPED', 'Shipped'
        INVOICED = 'INVOICED', 'Invoiced'
        CREDIT_HOLD = 'CREDIT_HOLD', 'Credit Hold'

    so_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    selling_node = models.ForeignKey(Node, on_delete=models.RESTRICT, related_name='sales_orders')
    customer_bp = models.ForeignKey(BusinessPartner, on_delete=models.RESTRICT, related_name='sales_orders')
    order_status = models.CharField(max_length=30, choices=OrderStatus.choices, default=OrderStatus.DRAFT)
    incoterms = models.CharField(max_length=3)  # e.g., 'EXW', 'DDP'
    total_value = models.DecimalField(max_digits=19, decimal_places=4, default=0.0000)

    class Meta:
        db_table = 'com\".\"sales_orders'
        indexes = [
            models.Index(fields=['customer_bp'], name='idx_so_customer'),
            models.Index(fields=['order_status'], name='idx_so_status'),
        ]


class SOLine(models.Model):
    """
    The Demand.
    Decoupled from the SO Header, meaning Line 1 can ship from NY, and Line 2 from TX.
    """
    so_line_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    so = models.ForeignKey(SalesOrder, on_delete=models.CASCADE, related_name='lines')
    item = models.ForeignKey(Item, on_delete=models.RESTRICT)
    fulfilling_node = models.ForeignKey(Node, on_delete=models.RESTRICT)
    requested_qty = models.DecimalField(max_digits=19, decimal_places=4)
    promised_date = models.DateField()  # Strict DATE, decoupled from TZ

    class Meta:
        db_table = 'com\".\"so_lines'
        indexes = [
            models.Index(fields=['fulfilling_node', 'item'], name='idx_sol_node_item'),
            models.Index(fields=['promised_date'], name='idx_sol_promised'),
        ]


class Shipment(TimeStampedModel):
    """
    The Freight Manifest.
    The physical vehicle/vessel leaving the facility, carrying multiple Deliveries.
    """
    class ShipmentStatus(models.TextChoices):
        PLANNED = 'PLANNED', 'Planned'
        STAGED = 'STAGED', 'Staged'
        DISPATCHED = 'DISPATCHED', 'Dispatched'
        DELIVERED = 'DELIVERED', 'Delivered'

    shipment_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    origin_node = models.ForeignKey(Node, on_delete=models.RESTRICT)  # Dock Node
    carrier_bp = models.ForeignKey(BusinessPartner, on_delete=models.RESTRICT)
    tracking_number = models.CharField(max_length=100, null=True, blank=True)
    freight_cost = models.DecimalField(max_digits=19, decimal_places=4, default=0.0000)
    dispatch_time = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=30, choices=ShipmentStatus.choices, default=ShipmentStatus.PLANNED)

    class Meta:
        db_table = 'com\".\"shipments'
        indexes = [
            models.Index(fields=['carrier_bp'], name='idx_shipment_carrier'),
        ]


class OutboundDelivery(TimeStampedModel):
    """
    The Logistical Bridge.
    The instruction linking Customer Demand to WMS Warehouse Tasks.
    """
    class DeliveryStatus(models.TextChoices):
        PENDING_WMS = 'PENDING_WMS', 'Pending WMS'
        PICKING = 'PICKING', 'Picking'
        PACKED = 'PACKED', 'Packed'
        SHIPPED = 'SHIPPED', 'Shipped'

    delivery_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    so_line = models.ForeignKey(SOLine, on_delete=models.RESTRICT, related_name='deliveries')
    shipment = models.ForeignKey(Shipment, on_delete=models.SET_NULL, null=True, blank=True, related_name='deliveries')
    node = models.ForeignKey(Node, on_delete=models.RESTRICT)  # Warehouse executing
    packed_lpn = models.ForeignKey(LPN, on_delete=models.SET_NULL, null=True, blank=True)
    delivery_status = models.CharField(max_length=30, choices=DeliveryStatus.choices, default=DeliveryStatus.PENDING_WMS)
    delivered_qty = models.DecimalField(max_digits=19, decimal_places=4, default=0.0000)

    class Meta:
        db_table = 'com\".\"outbound_deliveries'
        indexes = [
            models.Index(fields=['shipment'], name='idx_dlv_shipment'),
            models.Index(fields=['delivery_status'], name='idx_dlv_status'),
        ]

2. commercial/selectors.py
These functions strictly handle database reads. Crucially, the check_atp function leverages the architectural CQRS pattern to prevent locking WMS tables during checkout.
from uuid import UUID
from typing import Optional
from decimal import Decimal
from django.db.models import QuerySet
from commercial.models import SalesOrder, Shipment

def get_sales_order_details(so_id: UUID) -> Optional[SalesOrder]:
    """Fetches SO with pre-fetched Lines and Deliveries."""
    ...

def check_atp_cache(item_id: UUID, node_id: UUID, requested_qty: Decimal) -> bool:
    """
    CQRS Pattern (Blueprint Section 5).
    DO NOT QUERY WMS base tables. This selector strictly reads an O(1) 
    Redis Hash maintained asynchronously to evaluate:
    (Total On-Hand) - (Total Allocated) + (Incoming POs) >= requested_qty.
    """
    ...

def get_pending_deliveries_for_consolidation(origin_node_id: UUID) -> QuerySet:
    """Finds all PACKED Deliveries at a Node without an assigned Shipment."""
    ...

3. commercial/services.py
Strictly state-changing logic. This dictates how demand flows into the warehouse and how shipments are wrapped.
from uuid import UUID
from decimal import Decimal
from django.db import transaction
from commercial.models import SalesOrder, SOLine, OutboundDelivery, Shipment
from wms.services import allocate_inventory
from core.exceptions import BusinessRuleViolation

def create_sales_order(customer_bp_id: UUID, selling_node_id: UUID, incoterms: str, lines_data: list[dict]) -> SalesOrder:
    """
    Instantiates the SO and its lines.
    """
    ...

@transaction.atomic
def generate_outbound_delivery(so_id: UUID) -> list[OutboundDelivery]:
    """
    Strict Allocation Handoff.
    1. Checks the Law of Credit Governance (queries Finance).
       If over limit -> flips SO to CREDIT_HOLD.
    2. Iterates over SOLines.
    3. Calls 'wms.services.allocate_inventory()' to formally generate Pick Tasks.
    4. Creates OutboundDelivery records bridging the SO Lines to the Tasks.
    """
    ...




















































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































































def consolidate_shipment(origin_node_id: UUID, carrier_bp_id: UUID, delivery_ids: list[UUID]) -> Shipment:
    """
    Shipment Consolidation (Blueprint Section 6).
    Groups Deliveries onto a single Freight Manifest.
    """
    ...

def dispatch_shipment(shipment_id: UUID) -> Shipment:
    """
    Post Goods Issue (PGI) Execution.
    1. Locks the Shipment row.
    2. Flips Shipment to DISPATCHED.
    3. Triggers async Post Goods Issue task (deducting WMS inventory entirely).
    4. Triggers async Revenue Recognition task (Finance) based on Incoterms.
    """
    ...

4. commercial/forms.py
Replaces DRF for payload validation on Sales Orders and Shipments.
from django import forms

class CreateSOForm(forms.Form):
    customer_bp_id = forms.UUIDField(required=True)
    selling_node_id = forms.UUIDField(required=True)
    incoterms = forms.CharField(max_length=3, required=True)
    # lines_data is a JSON payload of items, nodes, and quantities
    lines_data = forms.JSONField(required=True)

class GenerateDeliveryForm(forms.Form):
    so_id = forms.UUIDField(required=True)

class DispatchShipmentForm(forms.Form):
    shipment_id = forms.UUIDField(required=True)

5. commercial/views.py
Traffic controllers designed to respond instantly to E-Commerce checkouts and shipping dock actions.
import json
from django.http import JsonResponse, HttpRequest
from django.views import View
from commercial.forms import CreateSOForm, GenerateDeliveryForm, DispatchShipmentForm
from commercial.services import create_sales_order, generate_outbound_delivery, dispatch_shipment

class SalesOrderAPIView(View):
    def post(self, request: HttpRequest) -> JsonResponse:
        ...

class OutboundDeliveryAPIView(View):
    def post(self, request: HttpRequest) -> JsonResponse:
        """Endpoint hit to release an SO to the Warehouse."""
        ...

class ShipmentDispatchAPIView(View):
    def post(self, request: HttpRequest) -> JsonResponse:
        """Endpoint hit by the Dock Manager to finalize the truck."""
        ...

6. commercial/tasks.py
Crucial isolation barrier. When a truck leaves, deducting 10,000 inventory items and posting 10,000 journal entries cannot be synchronous.
from celery import shared_task
from uuid import UUID

@shared_task
def execute_post_goods_issue(shipment_id: UUID) -> None:
    """
    The Immutable PGI.
    1. Reads all Deliveries on the Shipment.
    2. Drops the WMS InventoryPosition records.
    3. If Incoterms == 'EXW', immediately queues Finance Revenue Recognition.
    """
    ...

@shared_task
def update_atp_redis_hash(item_id: UUID, node_id: UUID) -> None:
    """
    Event-driven listener. Whenever WMS/MES/Procurement changes supply/demand,
    this background worker recalculates the O(1) cache for the Check_ATP selector.
    """
    ...


Architectural Review
Decoupled Flow: An SO is not a Shipment. The split between SO Line -> OutboundDelivery -> Shipment ensures that one order can be fulfilled by two warehouses and grouped onto two different trucks efficiently.
Cross-Boundary Execution: generate_outbound_delivery correctly calls the specific wms.services.allocate_inventory. It respects the boundary and delegates the row-level locking to the WMS layer.
The Asynchronous PGI: The dispatch_shipment service updates the Shipment status and immediately returns to the dock manager. The execute_post_goods_issue Celery task handles the heavy lifting, ensuring the dock scanner never times out.
Next Step:
Now that we have covered the outbound flow, we must govern the inbound flow. Shall we proceed to Procurement & Sourcing (procurement), which manages PRs, POs, and the strict 3-Way Match logic?
