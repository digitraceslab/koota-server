from __future__ import unicode_literals

from django.db import models
from django.contrib.auth.models import User
from django.conf import settings

# Create your models here.

class Data(models.Model):
    device_id = models.CharField(max_length=64)
    ts = models.DateTimeField(auto_now_add=True)
    ip = models.GenericIPAddressField()
    data = models.TextField(blank=True)

class UserDevice(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL)
    type = models.CharField(max_length=32)
    device_id = models.CharField(max_length=64)
    active = models.BooleanField(default=True)
