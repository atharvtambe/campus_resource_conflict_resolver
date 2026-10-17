from django.contrib import admin
from .models import Booking, BookingHistory


class BookingHistoryInline(admin.TabularInline):
    model = BookingHistory
    extra = 0
    can_delete = False
    readonly_fields = ('changed_by', 'old_status', 'new_status', 'changed_at', 'remarks')


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('id', 'resource', 'user', 'start_time', 'end_time', 'status', 'created_at')
    list_filter = ('status', 'resource__resource_type', 'start_time', 'created_at')
    search_fields = ('user__username', 'user__email', 'resource__name', 'purpose')
    ordering = ('-created_at',)
    inlines = [BookingHistoryInline]
    date_hierarchy = 'start_time'


@admin.register(BookingHistory)
class BookingHistoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'booking', 'changed_by', 'old_status', 'new_status', 'changed_at')
    list_filter = ('old_status', 'new_status', 'changed_at')
    search_fields = ('booking__resource__name', 'changed_by__username', 'remarks')
    ordering = ('-changed_at',)
    readonly_fields = ('booking', 'changed_by', 'old_status', 'new_status', 'changed_at', 'remarks')
