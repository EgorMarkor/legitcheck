from rest_framework import serializers
from .models import User, Verdict, VerdictPhoto, Payment


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = '__all__'


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
        fields = '__all__'


class PaymentSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    user_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        source='user',
        write_only=True
    )

    class Meta:
        model = Payment
        fields = '__all__'
