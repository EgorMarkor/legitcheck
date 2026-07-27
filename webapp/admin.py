# admin.py
from django.contrib import admin
from django.http import HttpResponse
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.text import slugify
from .models import (
    HomePagePopularItem,
    Payment,
    PromoCode,
    PromoCodeRedemption,
    UploadedVerdictPhoto,
    User,
    Verdict,
    VerdictPhoto,
    VkConversation,
    VkMessage,
    WebPushSubscription,
    NativePushDevice,
)
from unfold.admin import ModelAdmin  # вы используете свой класс-расширение
from io import BytesIO
import zipfile

class VerdictPhotoInline(admin.TabularInline):
    model = VerdictPhoto
    extra = 3         # сколько пустых полей для загрузки по умолчанию
    max_num = 10      # ограничение по кол-ву фотографий (по желанию)
    verbose_name = "Фото вердикта"
    verbose_name_plural = "Фотографии вердикта"

class VerdictAdmin(ModelAdmin):
    list_display = [
        'user_name',
        'brand',
        'item_model',
        'category_display',
        'status_display',
        'created_at',
        'download_verdict_link',
    ]
    list_filter = ['status', 'category', 'created_at']
    search_fields = ['user__name', 'user__username', 'brand', 'item_model', 'code']
    list_select_related = ['user']
    actions = ['approve_verdicts', 'reject_verdicts', 'download_selected_archives']
    inlines = [VerdictPhotoInline]  # <-- вот оно!

    def approve_verdicts(self, request, queryset):
        queryset.update(status='legit')
        self.message_user(request, "Выбранные вердикты одобрены")
    approve_verdicts.short_description = "Одобрить выбранные вердикты"

    def reject_verdicts(self, request, queryset):
        queryset.update(status='fake')
        self.message_user(request, "Выбранные вердикты отклонены")
    reject_verdicts.short_description = "Отклонить выбранные вердикты"

    def user_name(self, obj):
        return obj.user.name
    user_name.short_description = "Пользователь"

    def category_display(self, obj):
        return obj.get_category_display()
    category_display.short_description = "Категория"

    def status_display(self, obj):
        return obj.get_status_display()
    status_display.short_description = "Статус"

    def download_verdict_link(self, obj):
        url = reverse('admin:webapp_verdict_download', args=[obj.id])
        return format_html('<a class="button" href="{}">Скачать</a>', url)
    download_verdict_link.short_description = "Скачать"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                '<int:verdict_id>/download/',
                self.admin_site.admin_view(self.download_verdict),
                name='webapp_verdict_download',
            ),
        ]
        return custom_urls + urls

    def download_verdict(self, request, verdict_id):
        verdict = Verdict.objects.prefetch_related('photos').get(pk=verdict_id)
        response = self._build_zip_response([verdict])
        filename = f"verdict_{verdict.id}_{verdict.code}.zip"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    def download_selected_archives(self, request, queryset):
        verdicts = queryset.prefetch_related('photos')
        response = self._build_zip_response(verdicts)
        response['Content-Disposition'] = 'attachment; filename="verdicts_archive.zip"'
        return response
    download_selected_archives.short_description = "Скачать архив выбранных вердиктов"

    def _build_zip_response(self, verdicts):
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for verdict in verdicts:
                folder_name = slugify(f"verdict-{verdict.id}-{verdict.code}") or f"verdict-{verdict.id}"
                info_lines = [
                    f"Код: {verdict.code}",
                    f"Пользователь: {verdict.user.name}",
                    f"Категория: {verdict.get_category_display()}",
                    f"Бренд: {verdict.brand}",
                    f"Модель: {verdict.item_model}",
                    f"Статус: {verdict.get_status_display()}",
                    f"Комментарий пользователя: {verdict.comment_from_user}",
                ]
                zf.writestr(f"{folder_name}/info.txt", "\n".join(info_lines))

                for photo in verdict.photos.all():
                    try:
                        with photo.image.open('rb') as file_data:
                            filename = photo.image.name.split('/')[-1]
                            zf.writestr(f"{folder_name}/{filename}", file_data.read())
                    except FileNotFoundError:
                        continue

        buffer.seek(0)
        response = HttpResponse(buffer.getvalue(), content_type='application/zip')
        return response

class UserAdmin(ModelAdmin):
    list_display = ['tgId', 'name', 'username', 'is_free_check_available', 'next_free_check_timestamp']
    list_filter = ['is_free_check_available']
    search_fields = ['name', 'username']
    list_per_page = 20

class PaymentAdmin(ModelAdmin):
    list_display = ['uuid', 'user', 'amount', 'status', 'date']
    list_filter = ['status', 'date']
    search_fields = ['user__name', 'uuid']


class UploadedVerdictPhotoAdmin(ModelAdmin):
    list_display = ('id', 'user', 'created_at', 'used_at', 'verdict')
    list_filter = ('created_at', 'used_at')
    search_fields = ('user__name', 'user__username', 'user__tgId')


class HomePagePopularItemAdmin(ModelAdmin):
    list_display = (
        "position_display",
        "title",
        "subtitle",
        "views_count",
        "legit_percent",
        "fake_percent",
        "image_preview",
    )
    ordering = ("position",)
    search_fields = ("title", "subtitle")
    readonly_fields = ("image_preview", "updated_at")
    list_per_page = 5
    fieldsets = (
        (
            None,
            {
                "fields": ("position", "title", "subtitle"),
            },
        ),
        (
            "Статистика",
            {
                "fields": ("views_count", "legit_percent", "fake_percent"),
            },
        ),
        (
            "Изображение",
            {
                "fields": ("image", "fallback_image", "image_preview"),
            },
        ),
        (
            "Служебное",
            {
                "fields": ("updated_at",),
            },
        ),
    )

    def position_display(self, obj):
        return f"#{obj.position}"

    position_display.short_description = "Позиция"

    def image_preview(self, obj):
        if not obj:
            return "—"
        return format_html(
            '<img src="{}" style="width: 88px; height: 88px; object-fit: cover; border-radius: 12px;" alt="{}" />',
            obj.image_url,
            obj.full_title,
        )

    image_preview.short_description = "Превью"

    def has_add_permission(self, request):
        return super().has_add_permission(request) and self.model.objects.count() < 5

    def has_delete_permission(self, request, obj=None):
        return False


class PromoCodeAdmin(ModelAdmin):
    list_display = ("code", "reward_amount", "is_active", "created_at", "updated_at")
    list_filter = ("is_active", "created_at")
    search_fields = ("code",)
    readonly_fields = ("created_at", "updated_at")


class PromoCodeRedemptionAdmin(ModelAdmin):
    list_display = ("promo_code", "user", "amount", "created_at")
    search_fields = ("promo_code__code", "user__name", "user__username", "user__tgId")
    list_filter = ("created_at",)
    readonly_fields = ("promo_code", "user", "amount", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class VkConversationAdmin(ModelAdmin):
    list_display = ("peer_id", "title", "from_id", "unread_count", "last_message_at")
    search_fields = ("title", "peer_id", "from_id")
    list_filter = ("last_message_at",)
    readonly_fields = ("updated_at",)


class VkMessageAdmin(ModelAdmin):
    list_display = ("id", "conversation", "direction", "vk_message_id", "created_at")
    search_fields = ("text", "peer_id", "from_id", "vk_message_id")
    list_filter = ("direction", "created_at")
    readonly_fields = ("stored_at",)


class WebPushSubscriptionAdmin(ModelAdmin):
    list_display = ("id", "user", "active", "updated_at", "endpoint_preview")
    list_filter = ("active", "created_at", "updated_at")
    search_fields = ("endpoint", "user_agent", "last_error")
    readonly_fields = ("created_at", "updated_at", "last_error")

    def endpoint_preview(self, obj):
        return obj.endpoint[:80]

    endpoint_preview.short_description = "Endpoint"


class NativePushDeviceAdmin(ModelAdmin):
    list_display = ("id", "user", "platform", "environment", "active", "updated_at")
    list_filter = ("platform", "environment", "active", "updated_at")
    search_fields = ("user__tgId", "user__name", "token", "last_error")
    readonly_fields = ("created_at", "updated_at", "last_error")


admin.site.register(User, UserAdmin)
admin.site.register(Verdict, VerdictAdmin)
admin.site.register(UploadedVerdictPhoto, UploadedVerdictPhotoAdmin)
admin.site.register(Payment, PaymentAdmin)
admin.site.register(HomePagePopularItem, HomePagePopularItemAdmin)
admin.site.register(PromoCode, PromoCodeAdmin)
admin.site.register(PromoCodeRedemption, PromoCodeRedemptionAdmin)
admin.site.register(VkConversation, VkConversationAdmin)
admin.site.register(VkMessage, VkMessageAdmin)
admin.site.register(WebPushSubscription, WebPushSubscriptionAdmin)
admin.site.register(NativePushDevice, NativePushDeviceAdmin)
