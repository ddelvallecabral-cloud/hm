"""Tests: igual que dev pero con hashing rápido."""
from .dev import *  # noqa: F401,F403

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
