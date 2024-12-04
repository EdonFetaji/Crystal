from django.contrib import admin
from .models import Stock, ApplicationUser
from django.core.management import call_command
from django.contrib import messages
from django.http import HttpResponseRedirect

# Register your models here.

@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'mse_url', 'cloud_key', 'last_modified']
    search_fields = ['code', 'name']
    readonly_fields = ['last_modified']
    
    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path('populate-stocks/', self.populate_stocks, name='populate-stocks'),
        ]
        return custom_urls + urls
    
    def populate_stocks(self, request):
        try:
            call_command('populate_stocks')
            self.message_user(request, "Successfully populated stocks from MSE!", messages.SUCCESS)
        except Exception as e:
            self.message_user(request, f"Error populating stocks: {str(e)}", messages.ERROR)
        return HttpResponseRedirect("../")
    
    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['show_populate_button'] = True
        return super().changelist_view(request, extra_context=extra_context)

@admin.register(ApplicationUser)
class ApplicationUserAdmin(admin.ModelAdmin):
    list_display = ('user', 'get_email', 'created_at')
    search_fields = ('user__email', 'user__username')
    filter_horizontal = ('watchlist',)

    def get_email(self, obj):
        return obj.user.email
    get_email.short_description = 'Email'
