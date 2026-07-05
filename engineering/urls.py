from django.urls import path
from engineering.views import BOMRegistryView, BOMLineView, ECOExecutionView

urlpatterns = [
    path('boms/', BOMRegistryView.as_view(), name='bom-registry'),
    path('boms/<uuid:bom_id>/lines/', BOMLineView.as_view(), name='bom-lines'),
    path('ecos/<uuid:eco_id>/execute/', ECOExecutionView.as_view(), name='eco-execute'),
]