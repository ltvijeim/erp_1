from django.urls import path
from mdm.views import ItemRegistryView, ItemNodeExtensionView, BusinessPartnerRoleView

urlpatterns = [
    path('items/', ItemRegistryView.as_view(), name='item-registry'),
    path('items/<uuid:item_id>/', ItemRegistryView.as_view(), name='item-detail'),
    path('items/<uuid:item_id>/extensions/', ItemNodeExtensionView.as_view(), name='item-extension'),
    path('items/<uuid:item_id>/extensions/<uuid:node_id>/', ItemNodeExtensionView.as_view(), name='item-extension-detail'),
    path('partners/roles/', BusinessPartnerRoleView.as_view(), name='bp-role'),
]