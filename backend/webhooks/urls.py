from django.urls import path
from . import views

urlpatterns = [
    path('zenclass/', views.zenclass_webhook, name='zenclass_webhook'),
]
