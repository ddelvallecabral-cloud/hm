from django.contrib.auth.models import AbstractUser


class Usuario(AbstractUser):
    """Modelo de usuario propio, definido desde el inicio.

    Django no permite cambiar AUTH_USER_MODEL fácilmente una vez creadas las
    migraciones, por eso existe ya en el esqueleto. Los roles (administrador,
    tesorero, cobrador) se agregan en la etapa de seguridad.
    """

    class Meta:
        db_table = "usuarios"
