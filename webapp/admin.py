# admin.py
from django.contrib import admin
from .models import User, Verdict, VerdictPhoto, Payment
from unfold.admin import ModelAdmin  # вы используете свой класс-расширение

class VerdictPhotoInline(admin.TabularInline):
    model = VerdictPhoto
    extra = 3         # сколько пустых полей для загрузки по умолчанию
    max_num = 10      # ограничение по кол-ву фотографий (по желанию)
    verbose_name = "Фото вердикта"
    verbose_name_plural = "Фотографии вердикта"

class VerdictAdmin(ModelAdmin):
    list_display = ['user', 'category', 'created_at']
    list_filter = ['category', 'created_at']
    search_fields = ['user__name', 'user__username']
    actions = ['approve_verdicts', 'reject_verdicts']
    inlines = [VerdictPhotoInline]  # <-- вот оно!

    def approve_verdicts(self, request, queryset):
        queryset.update(category='legit')
        self.message_user(request, "Выбранные вердикты одобрены")
    approve_verdicts.short_description = "Одобрить выбранные вердикты"

    def reject_verdicts(self, request, queryset):
        queryset.update(category='fake')
        self.message_user(request, "Выбранные вердикты отклонены")
    reject_verdicts.short_description = "Отклонить выбранные вердикты"

class UserAdmin(ModelAdmin):
    list_display = ['tgId', 'name', 'username']
    search_fields = ['name', 'username']
    list_per_page = 20

class PaymentAdmin(ModelAdmin):
    list_display = ['uuid', 'user', 'amount', 'status', 'date']
    list_filter = ['status', 'date']
    search_fields = ['user__name', 'uuid']

admin.site.register(User, UserAdmin)
admin.site.register(Verdict, VerdictAdmin)
admin.site.register(Payment, PaymentAdmin)
