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