from django import forms

class CreateWorkOrderForm(forms.Form):
    item_id = forms.UUIDField(required=True)
    node_id = forms.UUIDField(required=True)
    target_quantity = forms.DecimalField(max_digits=19, decimal_places=4, min_value=0.0001, required=True)

class MaterialIssueForm(forms.Form):
    component_item_id = forms.UUIDField(required=True)
    work_center_id = forms.UUIDField(required=True)
    scanned_qty = forms.DecimalField(max_digits=19, decimal_places=4, min_value=0.0001, required=True)
    batch_serial_ref = forms.CharField(max_length=100, required=True)  # Traceability mandate

class OperationYieldForm(forms.Form):
    yield_qty = forms.DecimalField(max_digits=19, decimal_places=4, min_value=0.0001, required=True)
    work_center_id = forms.UUIDField(required=True)