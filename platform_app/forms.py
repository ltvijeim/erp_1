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