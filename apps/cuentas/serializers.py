from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(error_messages={"invalid": "Escribe un correo válido.", "required": "Escribe tu correo."})
    password = serializers.CharField(error_messages={"required": "Escribe tu contraseña.", "blank": "Escribe tu contraseña."})


class CambiarPasswordSerializer(serializers.Serializer):
    actual = serializers.CharField()
    nueva = serializers.CharField(min_length=8)

    def validate_nueva(self, valor):
        validate_password(valor, self.context["request"].user)
        return valor


class PushTokenSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=200, allow_blank=True)
