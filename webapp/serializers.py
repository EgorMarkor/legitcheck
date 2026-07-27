from rest_framework import serializers
from .models import User, Verdict, VerdictPhoto, Payment


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'tgId',
            'img',
            'name',
            'balance',
            'is_free_check_available',
            'next_free_check_timestamp',
            'username',
            'email',
        ]
        read_only_fields = fields


class VerdictPhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = VerdictPhoto
        fields = ['id', 'image', 'uploaded_at']


class VerdictSerializer(serializers.ModelSerializer):
    photos = VerdictPhotoSerializer(many=True, read_only=True)
    user = UserSerializer(read_only=True)
    user_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        source='user',
        write_only=True
    )

    class Meta:
        model = Verdict
        fields = [
            'id',
            'photos',
            'user',
            'user_id',
            'status',
            'category',
            'brand',
            'item_model',
            'created_at',
            'comment',
            'comment_from_user',
            'code',
            'speed',
            'price',
            'with_reason',
            'idempotency_key',
        ]


class PaymentSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    user_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        source='user',
        write_only=True
    )

    class Meta:
        model = Payment
        fields = [
            'uuid',
            'user',
            'user_id',
            'amount',
            'status',
            'date',
            'provider_payment_id',
        ]
