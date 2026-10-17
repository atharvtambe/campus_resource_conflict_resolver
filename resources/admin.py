from django.contrib import admin
from .models import Resource, ResourceBlock


@admin.register(Resource)
class ResourceAdmin(admin.ModelAdmin):
    list_display = ('name', 'resource_type', 'location', 'capacity', 'is_active', 'created_at')
    list_filter = ('resource_type', 'is_active', 'location')
    search_fields = ('name', 'location', 'description')
    ordering = ('name',)
    list_editable = ('is_active',)


@admin.register(ResourceBlock)
class ResourceBlockAdmin(admin.ModelAdmin):
    list_display = ('resource', 'start_time', 'end_time', 'reason', 'created_by', 'created_at')
    list_filter = ('resource', 'start_time')
    search_fields = ('resource__name', 'reason')
    ordering = ('-start_time',)
