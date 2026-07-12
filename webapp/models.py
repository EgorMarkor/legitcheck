import uuid

from django.db import models
from django.db.models import Q
from django.templatetags.static import static
from django.utils import timezone

from .image_utils import apply_verdict_photo_watermark

class User(models.Model):
    tgId = models.IntegerField(primary_key=True, verbose_name='Telegram ID')
    img = models.CharField(max_length=255, verbose_name='Profile Image URL')
    name = models.CharField(max_length=255, verbose_name='Full Name')
    balance = models.CharField(max_length=255, verbose_name="Баланс")
    is_free_check_available = models.BooleanField(
        default=True,
        verbose_name="Бесплатная проверка доступна",
    )
    next_free_check_timestamp = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Следующая бесплатная проверка",
    )
    username = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name='Telegram Username'
    )
    email = models.EmailField(
        max_length=255,
        null=True,
        blank=True,
        unique=True,
        verbose_name='Email'
    )
    auth_token = models.UUIDField(default=uuid.uuid4, unique=True)
    
    class Meta:
        verbose_name = "Пользователи"
        
    def __str__(self):
        return f"{self.name} (@{self.username})" if self.username else self.name

class Verdict(models.Model):
    CATEGORY_CHOICES = [
        ('inpending', 'В обработке'),
        ('todo', 'Требует действия'),
        ('fake', 'Подделка'),
        ('legit', 'Оригинал'),
        ('dont_payment', 'Не оплачено'),
    ]
    
    ITEM_CHOICES = [
        ('sneakers', 'Кроссовки'),
        ('clothes', 'Одежда'),
        ('bags', 'Сумки'),
        ('belts', 'Ремни'),
        ('watch', 'Часы'),
        ('cosmetics', 'Косметика'),
        ('jewerly', 'Украшения'),
        ('toys', 'Игрушки'),
        ('accsesory', 'Аксессуары'),
        ('others', 'Другое'),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='verdicts',
        verbose_name='Пользователь'
    )
    status = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        verbose_name='Категория нарушения'
    )
    
    category = models.CharField(
        max_length=30,
        choices=ITEM_CHOICES,
        verbose_name='Категория вещи'
    )
    
    brand = models.CharField(
        max_length=40,
        verbose_name='Бренд'
    )
    
    item_model = models.CharField(
        max_length=40,
        verbose_name='Модель'
    )
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    
    comment = models.CharField(max_length=9999)
    
    comment_from_user = models.CharField(max_length=9999, verbose_name="Комментарий пользователя")
    
    code = models.CharField(max_length=5, unique=True)
    
    speed = models.CharField(max_length=32)  # 24h / 15min-basic / 15min-expensive
    price = models.DecimalField(max_digits=10, decimal_places=2)
    with_reason = models.BooleanField(default=False)
    idempotency_key = models.CharField(max_length=64, null=True, blank=True, db_index=True)


    def __str__(self):
        return f"{self.user.name} - {self.get_category_display()}"
    
    class Meta:
        verbose_name = "Вердикты"
        verbose_name_plural = "Вердикты"  # Для корректного отображения множественного числа
        indexes = [
            models.Index(fields=["user", "-created_at"], name="verdict_user_created_idx"),
            models.Index(fields=["user", "code"], name="verdict_user_code_idx"),
            models.Index(fields=["status", "-created_at"], name="verdict_status_created_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "idempotency_key"],
                condition=Q(idempotency_key__isnull=False),
                name="unique_verdict_idempotency_key_per_user",
            ),
        ]
        
        
class VerdictPhoto(models.Model):
    verdict = models.ForeignKey(
        Verdict,
        on_delete=models.CASCADE,
        related_name='photos',
        verbose_name='Вердикт'
    )
    image = models.ImageField(
        upload_to='verdicts/photos',
        verbose_name='Фото'
    )
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name='Загружено')

    def __str__(self):
        return f"Фото {self.id} для вердикта {self.verdict.id}"

    def save(self, *args, **kwargs):
        if self.image and not getattr(self.image, "_committed", True):
            self.image = apply_verdict_photo_watermark(self.image.file)
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Фотография вердикта"
        verbose_name_plural = "Фотографии вердикта"
        ordering = ("id",)
        indexes = [
            models.Index(fields=["verdict", "id"], name="vphoto_verdict_id_idx"),
        ]


class UploadedVerdictPhoto(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='uploaded_verdict_photos',
    )
    image = models.ImageField(upload_to='verdicts/uploads')
    created_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True, blank=True)
    verdict = models.ForeignKey(
        Verdict,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='source_uploaded_photos',
    )

    class Meta:
        verbose_name = "Загруженная фотография вердикта"
        verbose_name_plural = "Загруженные фотографии вердикта"
        indexes = [
            models.Index(fields=["user", "verdict"], name="upload_user_verdict_idx"),
            models.Index(fields=["user", "-created_at"], name="upload_user_created_idx"),
        ]

    def save(self, *args, **kwargs):
        if self.image and not getattr(self.image, "_committed", True):
            self.image = apply_verdict_photo_watermark(self.image.file)
        super().save(*args, **kwargs)

    def mark_used(self, verdict):
        self.verdict = verdict
        self.used_at = timezone.now()
        self.save(update_fields=["verdict", "used_at"])


class HomePagePopularItem(models.Model):
    DEFAULT_ITEMS = (
        {
            "position": 1,
            "title": "Balenciaga Track",
            "subtitle": "White Orange",
            "fallback_image": "balenciaga_track.png",
            "views_count": 231,
            "legit_percent": 43,
            "fake_percent": 57,
        },
        {
            "position": 2,
            "title": "Balenciaga Track",
            "subtitle": "White Orange",
            "fallback_image": "balenciaga_track.png",
            "views_count": 231,
            "legit_percent": 43,
            "fake_percent": 57,
        },
        {
            "position": 3,
            "title": "Balenciaga Track",
            "subtitle": "White Orange",
            "fallback_image": "balenciaga_track.png",
            "views_count": 231,
            "legit_percent": 43,
            "fake_percent": 57,
        },
        {
            "position": 4,
            "title": "Balenciaga Track",
            "subtitle": "White Orange",
            "fallback_image": "balenciaga_track.png",
            "views_count": 231,
            "legit_percent": 43,
            "fake_percent": 57,
        },
        {
            "position": 5,
            "title": "Balenciaga Track",
            "subtitle": "White Orange",
            "fallback_image": "balenciaga_track.png",
            "views_count": 231,
            "legit_percent": 43,
            "fake_percent": 57,
        },
    )

    position = models.PositiveSmallIntegerField(
        unique=True,
        verbose_name="Позиция",
        help_text="Допустимы значения от 1 до 5.",
    )
    title = models.CharField(max_length=255, verbose_name="Название модели")
    subtitle = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Подзаголовок",
        help_text='Например: White Orange',
    )
    image = models.ImageField(
        upload_to="homepage/popular_models/",
        blank=True,
        null=True,
        verbose_name="Изображение",
    )
    fallback_image = models.CharField(
        max_length=255,
        default="balenciaga_track.png",
        verbose_name="Статическое изображение",
        help_text="Файл из каталога static/, используется если изображение не загружено.",
    )
    views_count = models.PositiveIntegerField(default=0, verbose_name="Количество просмотров")
    legit_percent = models.PositiveSmallIntegerField(default=0, verbose_name="Процент оригинала")
    fake_percent = models.PositiveSmallIntegerField(default=0, verbose_name="Процент подделок")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")

    class Meta:
        ordering = ["position"]
        verbose_name = "Популярная модель главной страницы"
        verbose_name_plural = "Топ-5 моделей главной страницы"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(position__gte=1, position__lte=5),
                name="webapp_homepagepopularitem_position_range",
            ),
            models.CheckConstraint(
                condition=models.Q(legit_percent__gte=0, legit_percent__lte=100),
                name="webapp_homepagepopularitem_legit_percent_range",
            ),
            models.CheckConstraint(
                condition=models.Q(fake_percent__gte=0, fake_percent__lte=100),
                name="webapp_homepagepopularitem_fake_percent_range",
            ),
        ]

    def __str__(self):
        return f"#{self.position} {self.full_title}"

    @property
    def full_title(self):
        if self.subtitle:
            return f'{self.title} "{self.subtitle}"'
        return self.title

    @property
    def image_url(self):
        if self.image:
            return self.image.url
        return static(self.fallback_image or "balenciaga_track.png")

    @classmethod
    def default_items(cls):
        return [cls(**item_data) for item_data in cls.DEFAULT_ITEMS]


class EmailOTPToken(models.Model):
    """OTP-код для входа по email. Действует 10 минут, одноразовый."""
    email = models.EmailField(verbose_name='Email')
    code = models.CharField(max_length=6, verbose_name='Код')
    created_at = models.DateTimeField(auto_now_add=True)
    used = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Email OTP"
        verbose_name_plural = "Email OTP"
        indexes = [
            models.Index(fields=["email", "used", "-created_at"], name="emailotp_lookup_idx"),
        ]

    @property
    def is_expired(self):
        return timezone.now() > self.created_at + timezone.timedelta(minutes=10)

    def __str__(self):
        return f"{self.email} — {self.code}"


class Payment(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Ожидает оплаты'),
        ('COMPLETED', 'Оплачено'),
        ('FAILED', 'Ошибка оплаты'),
    ]

    id = models.AutoField(primary_key=True)
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    date = models.DateTimeField(auto_now_add=True, verbose_name='Дата платежа')
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='PENDING',
        verbose_name='Статус'
    )
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='payments',
        verbose_name='Пользователь'
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='Сумма платежа'
    )
    
    provider_payment_id = models.CharField(
        max_length=255,
        null=True,
        blank=True
    )

    def __str__(self):
        return f"Payment {self.uuid} - {self.status}"
    
    class Meta:
        verbose_name = "Платежи"
        indexes = [
            models.Index(fields=["provider_payment_id"], name="payment_provider_idx"),
            models.Index(fields=["user", "-date"], name="payment_user_date_idx"),
            models.Index(fields=["status", "-date"], name="payment_status_date_idx"),
        ]


class TelegramVerdictDelivery(models.Model):
    verdict = models.OneToOneField(
        Verdict,
        on_delete=models.CASCADE,
        related_name="telegram_delivery",
    )
    chat_id = models.CharField(max_length=64)
    message_ids = models.JSONField(default=list, blank=True)
    interval_minutes = models.PositiveIntegerField()
    expires_at = models.DateTimeField(db_index=True)
    next_send_at = models.DateTimeField(db_index=True)
    active = models.BooleanField(default=True, db_index=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Доставка вердикта в Telegram"
        verbose_name_plural = "Доставки вердиктов в Telegram"
        indexes = [
            models.Index(fields=["active", "next_send_at"], name="tgdelivery_due_idx"),
        ]


class PromoCode(models.Model):
    code = models.CharField(
        max_length=64,
        unique=True,
        verbose_name="Промокод",
        help_text="Сохраняется в верхнем регистре.",
    )
    reward_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Сумма начисления",
    )
    is_active = models.BooleanField(default=True, verbose_name="Активен")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлен")

    class Meta:
        verbose_name = "Промокод"
        verbose_name_plural = "Промокоды"
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.code} (+{self.reward_amount})"

    def save(self, *args, **kwargs):
        self.code = (self.code or "").strip().upper()
        super().save(*args, **kwargs)


class PromoCodeRedemption(models.Model):
    promo_code = models.ForeignKey(
        PromoCode,
        on_delete=models.CASCADE,
        related_name="redemptions",
        verbose_name="Промокод",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="promo_code_redemptions",
        verbose_name="Пользователь",
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Начислено",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Активирован")

    class Meta:
        verbose_name = "Активация промокода"
        verbose_name_plural = "Активации промокодов"
        unique_together = ("promo_code", "user")
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.user} / {self.promo_code.code}"


class VkConversation(models.Model):
    peer_id = models.BigIntegerField(unique=True, db_index=True, verbose_name="VK peer ID")
    from_id = models.BigIntegerField(db_index=True, verbose_name="VK user ID")
    title = models.CharField(max_length=255, blank=True, verbose_name="Название")
    avatar_url = models.URLField(max_length=500, blank=True, verbose_name="Аватар")
    last_message_text = models.TextField(blank=True, verbose_name="Последнее сообщение")
    last_message_at = models.DateTimeField(null=True, blank=True, db_index=True)
    unread_count = models.PositiveIntegerField(default=0, verbose_name="Новые сообщения")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "VK диалог"
        verbose_name_plural = "VK диалоги"
        ordering = ("-last_message_at", "-updated_at")
        indexes = [
            models.Index(fields=["-last_message_at", "-updated_at"], name="vkconv_last_updated_idx"),
        ]

    def __str__(self):
        return self.title or f"vk.com/id{self.from_id}"


class VkMessage(models.Model):
    DIRECTION_INCOMING = "incoming"
    DIRECTION_OUTGOING = "outgoing"
    DIRECTION_CHOICES = [
        (DIRECTION_INCOMING, "Входящее"),
        (DIRECTION_OUTGOING, "Исходящее"),
    ]

    conversation = models.ForeignKey(
        VkConversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    vk_message_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    peer_id = models.BigIntegerField(db_index=True)
    from_id = models.BigIntegerField(db_index=True)
    direction = models.CharField(max_length=16, choices=DIRECTION_CHOICES)
    text = models.TextField(blank=True)
    attachments = models.JSONField(default=list, blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(db_index=True)
    stored_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "VK сообщение"
        verbose_name_plural = "VK сообщения"
        ordering = ("created_at", "id")
        indexes = [
            models.Index(fields=["conversation", "-created_at", "-id"], name="vkmsg_conv_created_idx"),
            models.Index(fields=["peer_id", "-created_at"], name="vkmsg_peer_created_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("peer_id", "vk_message_id", "direction"),
                name="unique_vk_message_per_peer_direction",
            ),
        ]

    def __str__(self):
        return f"{self.direction} #{self.vk_message_id or self.id}"


class WebPushSubscription(models.Model):
    endpoint = models.TextField(unique=True)
    p256dh = models.TextField()
    auth = models.TextField()
    user_agent = models.TextField(blank=True)
    active = models.BooleanField(default=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Web Push подписка"
        verbose_name_plural = "Web Push подписки"
        ordering = ("-updated_at",)
        indexes = [
            models.Index(fields=["active", "-updated_at"], name="webpush_active_updated_idx"),
        ]

    def __str__(self):
        return self.endpoint[:80]
