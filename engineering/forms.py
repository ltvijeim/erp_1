from django import forms
from engineering.models import BOMHeader, EngineeringChangeOrder

class DraftBOMForm(forms.Form):
    item_id = forms.UUIDField(required=True)
    node_id = forms.UUIDField(required=True)
    bom_type = forms.ChoiceField(choices=BOMHeader.BOMType.choices, required=True)
    revision_level = forms.CharField(max_length=50, required=True)

class BOMLineForm(forms.Form):
    component_item_id = forms.UUIDField(required=True)
    quantity = forms.DecimalField(max_digits=19, decimal_places=4, required=True, min_value=0.0001)
    scrap_factor = forms.DecimalField(max_digits=5, decimal_places=4, required=False, initial=0.0)
    valid_from = forms.DateField(required=False)
    valid_to = forms.DateField(required=False)

class ECOApprovalForm(forms.Form):
    effectivity_date = forms.DateTimeField(required=True)