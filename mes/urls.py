from django.urls import path
from mes.views import WorkOrderAPIView, MaterialIssueAPIView, WorkOrderCompletionView

urlpatterns = [
    path('work-orders/', WorkOrderAPIView.as_view(), name='wo-create'),
    path('work-orders/<uuid:wo_id>/issue-material/', MaterialIssueAPIView.as_view(), name='wo-issue-material'),
    path('work-orders/<uuid:wo_id>/complete/', WorkOrderCompletionView.as_view(), name='wo-complete'),
]