from django import forms
from mdm.models import Item, ItemNodeExtension, BPNodeRole

class CreateItemForm(forms.Form):
    sku = forms.CharField(max_length=100, required=True)
    item_class = forms.ChoiceField(choices=Item.ItemClass.choices, required=True)
    base_uom = forms.CharField(max_length=20, required=True)
    global_description = forms.CharField(required=True, widget=forms.Textarea)
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