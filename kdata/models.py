from __future__ import unicode_literals

from django.db import models
from django.contrib.auth.models import User
from django.conf import settings

from . import devices
# Create your models here.

class Data(models.Model):
    class Meta:
        index_together = [
            ["device_id", "ts"],
            ]
    device_id = models.CharField(max_length=64)
    ts = models.DateTimeField(auto_now_add=True)
    ip = models.GenericIPAddressField()
    data = models.TextField(blank=True)

class Device(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL)
    name = models.CharField(max_length=64,
                            help_text='Give your device a name')
    type = models.CharField(max_length=32,
                            help_text='What type of device is this',
                            choices=devices.device_choices)
    device_id = models.CharField(max_length=64, primary_key=True)
    active = models.BooleanField(default=True)
