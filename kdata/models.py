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
    data_length = models.IntegerField(blank=True, null=True)
    data = models.TextField(blank=True)

class Device(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL)
    name = models.CharField(max_length=64,
                            help_text='Give your device a name')
    type = models.CharField(max_length=32,
                            help_text='What type of device is this',
                            choices=devices.device_choices)
    device_id = models.CharField(max_length=64, primary_key=True, unique=True)
    active = models.BooleanField(default=True)
    _public_id = models.CharField(db_column='public_id', max_length=64, null=True, blank=True, db_index=True)
    _secret_id = models.CharField(db_column='secret_id', max_length=64, null=True, blank=True, db_index=True)
    @property
    def public_id(self):
        """Device secret_id.  secret_id column, if missing then device_id[:6]"""
        if self._public_id:
            return self._public_id
        return self.device_id[:6]  # warning: 6 hardcoded here and device creation (and maybe more)
    @property
    def secret_id(self):
        """Device secret_id.  secret_id column, if missing then device_id"""
        if self._secret_id:
            return self._secret_id
        return self.device_id
    @classmethod
    def get_by_id(cls, public_id):
        """Get a Device object given its public_id.
        """
        # First check public_id column, if that is not found return
        # device that has device_id beginning with public_id.
        try:
            return cls.objects.get(_public_id=public_id)
        except cls.DoesNotExist:
            return cls.objects.get(device_id__startswith=public_id)
