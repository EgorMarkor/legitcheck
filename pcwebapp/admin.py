# pcwebapp/admin.py
from django.contrib import admin
from .models import LoginToken, Brand

@admin.register(LoginToken)
class LoginTokenAdmin(admin.ModelAdmin):
    list_display = ('token', 'user', 'telegram_id', 'ip_address', 'created_at', 'expires_at', 'used_at')
    list_filter  = ('created_at', 'expires_at', 'used_at')
    search_fields = ('token', 'user__username', 'telegram_id', 'ip_address')


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ('brand', 'brand_id', 'category')
    search_fields = ('brand', 'brand_id', 'category')
