from .base import *  # noqa: F401,F403
from .base import REST_FRAMEWORK

DEBUG = False
SECRET_KEY = "clave-solo-para-tests"
ALLOWED_HOSTS = ["*"]

# Los tests corren en SQLite en memoria: no necesitan MySQL encendido.
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {"login": "1000/min", "escanear": "1000/min"}
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
