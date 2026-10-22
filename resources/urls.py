from django.urls import path
from . import views

app_name = 'resources'

urlpatterns = [
    path('', views.resource_list, name='resource_list'),
    path('create/', views.resource_create, name='resource_create'),
    path('<int:pk>/', views.resource_detail, name='resource_detail'),
    path('<int:pk>/edit/', views.resource_edit, name='resource_edit'),
    path('<int:pk>/block/', views.resource_block_create, name='resource_block_create'),
]
