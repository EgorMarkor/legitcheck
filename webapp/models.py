from django.db import models
import uuid

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
    
    class Meta:
        verbose_name = "Пользователи"
        
    def __str__(self):
        return f"{self.name} (@{self.username})" if self.username else self.name

from django.db import models

class Verdict(models.Model):
    CATEGORY_CHOICES = [
        ('inpending', 'В обработке'),
        ('todo', 'Требует действия'),
        ('fake', 'Подделка'),
        ('legit', 'Оригинал'),
        ('dont_payment', 'Не оплачено'),
    ]
    
    ITEM_CHOICES = [
        ('boots', 'Кроссовки'),
        ('pants', 'Штаны'),
        ('hoodie', 'Худи'),
        ('belt', 'Ремень'),
        ('bag', 'Сумка'),
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

    def __str__(self):
        return f"Payment {self.uuid} - {self.status}"
    
    class Meta:
        verbose_name = "Платежи"
