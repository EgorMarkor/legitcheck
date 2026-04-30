import uuid

from django.db import models
from django.templatetags.static import static
from django.utils import timezone

class User(models.Model):
    tgId = models.IntegerField(primary_key=True, verbose_name='Telegram ID')
    img = models.CharField(max_length=255, verbose_name='Profile Image URL')
    name = models.CharField(max_length=255, verbose_name='Full Name')
    balance = models.CharField(max_length=255, verbose_name="Баланс")
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


    def __str__(self):
        return f"{self.user.name} - {self.get_category_display()}"
    
    class Meta:
        verbose_name = "Вердикты"
        verbose_name_plural = "Вердикты"  # Для корректного отображения множественного числа
        
        
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

    class Meta:
        verbose_name = "Фотография вердикта"
        verbose_name_plural = "Фотографии вердикта"


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
