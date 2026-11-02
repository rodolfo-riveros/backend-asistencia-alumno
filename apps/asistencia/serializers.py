from rest_framework import serializers

from .models import Justificacion, Registro

ESTADOS = ["P", "T", "F", "J"]


class JustificacionEntradaSerializer(serializers.Serializer):
    motivo = serializers.ChoiceField(choices=Justificacion.Motivo.values)
    detalle = serializers.CharField(max_length=300, allow_blank=True, required=False, default="")


class MarcaSerializer(serializers.Serializer):
    uuid_cliente = serializers.UUIDField()
    matricula_id = serializers.IntegerField()
    seccion_id = serializers.IntegerField()
    fecha = serializers.DateField()
    bloque_id = serializers.IntegerField(required=False, allow_null=True, default=None)
    estado = serializers.ChoiceField(choices=ESTADOS, allow_null=True)
    metodo = serializers.ChoiceField(choices=[Registro.Metodo.MANUAL, Registro.Metodo.QR], default=Registro.Metodo.MANUAL)
    marcado_en = serializers.DateTimeField(required=False, allow_null=True, default=None)
    dispositivo_id = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    justificacion = JustificacionEntradaSerializer(required=False, allow_null=True, default=None)
    motivo_cambio = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


class LoteSerializer(serializers.Serializer):
    marcas = serializers.ListField(child=serializers.DictField(), max_length=200, allow_empty=True)


class EscanearSerializer(serializers.Serializer):
    codigo = serializers.CharField(max_length=200)
    modo = serializers.ChoiceField(choices=["PUERTA", "SECCION"], default="PUERTA")
    seccion_id = serializers.IntegerField(required=False, allow_null=True, default=None)
    marcado_en = serializers.DateTimeField(required=False, allow_null=True, default=None)
    uuid_cliente = serializers.UUIDField(required=False, allow_null=True, default=None)
    dispositivo_id = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")

    def validate(self, datos):
        if datos["modo"] == "SECCION" and not datos.get("seccion_id"):
            raise serializers.ValidationError({"seccion_id": "Indica la sección en modo sección."})
        return datos


class CerrarSerializer(serializers.Serializer):
    fecha = serializers.DateField(required=False, allow_null=True, default=None)
    bloque_id = serializers.IntegerField(required=False, allow_null=True, default=None)


class JustificarSerializer(serializers.Serializer):
    motivo = serializers.ChoiceField(
        choices=Justificacion.Motivo.values, error_messages={"invalid_choice": "Elige un motivo."}
    )
    detalle = serializers.CharField(max_length=300, allow_blank=True, required=False, default="")
    foto = serializers.ImageField(required=False, allow_null=True, default=None)
