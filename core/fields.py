from django.db import models

class LtreeField(models.TextField):
    """
    Custom Django ORM field mapping to the PostgreSQL 'ltree' extension.
    Crucial for ultra-fast spatial search and hierarchy resolution in the Platform layer.
    """
    description = "PostgreSQL ltree field for hierarchical materialized paths"

    def db_type(self, connection) -> str:
        return 'ltree'

    def get_prep_value(self, value: str) -> str:
        if value is None:
            return value
        return str(value)

    def from_db_value(self, value: str, expression, connection) -> str:
        if value is None:
            return value
        return str(value)