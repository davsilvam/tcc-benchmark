"""
Configuracao do projeto bookapi — gerado por 'django-admin startproject' (Django 6.1.1)
e ajustado a secao 6 da especificacao funcional da API.

As remocoes em relacao ao template padrao (admin, auth, sessions, messages, staticfiles e
os middlewares correspondentes, validadores de senha, motor de templates) seguem o mesmo
criterio aplicado as demais implementacoes: incluir apenas o que a API utiliza. O
equivalente no Spring Boot e o conjunto de starters do pom.xml — web, data-jpa e
validation, sem seguranca nem camada de visao.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-kje#+)xu&$9ccb!f5k^cd_4vmkok43j=yc0(s$cwkrf2lec1-d",
)

# Modo de produção, depuração desabilitada (seção 6.1).
DEBUG = False

ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "api",
]

MIDDLEWARE = [
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "bookapi.urls"

TEMPLATES = []

WSGI_APPLICATION = "bookapi.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME", "tccbench"),
        "USER": os.environ.get("DB_USER", "bench"),
        "PASSWORD": os.environ.get("DB_PASSWORD", "bench"),
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
        # Pool de conexões do psycopg (Django 5.1+). O contrato fixa 10 conexões por
        # tratamento (seção 6.1), mas o Gunicorn executa 5 processos trabalhadores
        # (seção 6.2) e cada um mantém seu próprio pool. Dimensiona-se, portanto, o pool
        # por trabalhador de modo que o AGREGADO seja 10 — 5 x 2. Fixar 10 por trabalhador
        # abriria 50 conexões e deixaria o Django com cinco vezes a concorrência de banco
        # dos demais tratamentos.
        "OPTIONS": {
            "pool": {
                "min_size": int(os.environ.get("DB_POOL_SIZE", "2")),
                "max_size": int(os.environ.get("DB_POOL_SIZE", "2")),
                "timeout": 10,
            }
        },
        # CONN_MAX_AGE não se aplica quando o pool está ativo.
        "DISABLE_SERVER_SIDE_CURSORS": False,
    }
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = False
USE_TZ = True

# Cache de aplicação desabilitado (seção 6.1).
CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"},
}

# Nivel de log WARNING, sem log de requisições (seção 6.1).
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "WARNING"},
}
