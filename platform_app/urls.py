from django.urls import path
from platform_app.views import NodeRegistryView, NodeHierarchyView, NodeSettingsView

urlpatterns = [
    path('nodes/', NodeRegistryView.as_view(), name='node-registry'),
    path('nodes/<uuid:node_id>/descendants/', NodeHierarchyView.as_view(), name='node-descendants'),
    path('nodes/<uuid:node_id>/settings/', NodeSettingsView.as_view(), name='node-settings'),
]