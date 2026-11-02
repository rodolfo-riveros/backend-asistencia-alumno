from .base import *  # noqa: F401,F403
from .base import REST_FRAMEWORK, env

DEBUG = env.bool("DEBUG", default=True)
# En la red local el teléfono entra por la IP de la PC (192.168.x.x).
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["*"])

REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = [
    "rest_framework.renderers.JSONRenderer",
    "rest_framework.renderers.BrowsableAPIRenderer",
]
