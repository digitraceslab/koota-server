from __future__ import unicode_literals

from django.db import models
from django.contrib.auth.models import User
from django.conf import settings

from . import devices
from . import util
# Create your models here.

import logging
logger = logging.getLogger(__name__)

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
                            help_text='A descriptive name for your device.')
    type = models.CharField(max_length=128,
                            help_text='What type of device is this?',
                            choices=devices.get_choices(all=True))
    device_id = models.CharField(max_length=64, primary_key=True, unique=True)
    active = models.BooleanField(default=True)
    _public_id = models.CharField(db_column='public_id', max_length=64, null=True, blank=True, db_index=True)
    _secret_id = models.CharField(db_column='secret_id', max_length=64, null=True, blank=True, db_index=True)
    label = models.ForeignKey('DeviceLabel', null=True, blank=True, verbose_name="Usage",
                              help_text='How is this device used?  Primary means that you actively use the '
                                        ' device in your life, secondary is used by you sometimes. ')
    comment = models.CharField(max_length=256, null=True, blank=True, help_text='Any other comments to researchers (optional)')
#    ts_device_create = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        """String representation: Device(public_id)"""
        return 'Device(%s)'%self.public_id
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
        """Get a Device object given its public_id or device_id.
        """
        # First check public_id column, if that is not found return
        # device that has device_id beginning with public_id.
        if len(public_id) < 6:
            raise Http404
        try:
            return cls.objects.get(_public_id=public_id)
        except cls.DoesNotExist:
            return cls.objects.get(device_id__startswith=public_id)
    def get_class(self):
        """Return the Python class corresponding to this device."""
        cls = devices.get_class(self.type)
        return cls(self)
    def human_name(self):
        cls = self.get_class()
        # super object does notwork with .get_FOO_display()
        #return super(Device, self).get_type_display()
        return self.get_type_display()
# See comment in kdata.devices.register_device to know why this is
# here. It is a hack to work around a circular import.
Device._meta.get_field('type').choices = devices.all_device_choices



class DeviceLabel(models.Model):
    name = models.CharField(max_length=64, null=True, blank=True)
    description = models.CharField(max_length=256, null=True, blank=True)
    def __str__(self):
        return self.name


class Group(models.Model):
    slug = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=64)
    desc = models.CharField(max_length=64)
    active = models.BooleanField(default=True)
    pyclass = models.CharField(max_length=128, blank=True, null=True)
    pyclass_data = models.CharField(max_length=256, blank=True, null=True)
    url = models.CharField(max_length=256, blank=True, null=True)
    ts_start = models.DateTimeField(blank=True, null=True)
    ts_end = models.DateTimeField(blank=True, null=True)
    invite_code = models.CharField(max_length=64)
    otp_required = models.BooleanField(default=False,
                                       help_text="Require OTP auth for researchers?")
    subjects = models.ManyToManyField(settings.AUTH_USER_MODEL,
                                      through='GroupSubject',
                                      related_name='subject_of_groups',
                                      swappable=True)
    researchers = models.ManyToManyField(settings.AUTH_USER_MODEL,
                                         through='GroupResearcher',
                                         related_name='researcher_of_groups',
                                         swappable=True)
    def __str__(self):
        return self.name
    def n_subjects(self):
        return self.subjects.count()
    def n_researchers(self):
        return self.researchers.count()
    def get_class(self):
        cls = util.import_by_name(self.pyclass, default=group.BaseGroup)
        return cls(self)
    def is_subject(self, user):
        """Is given user a subject of this group?"""
        return self.subjects.filter(groupsubject__user=user).exists()
    def is_researcher(self, user):
        """Is given user a researcher of this group?"""
        return self.researchers.filter(groupresearcher__user=user).exists()


class GroupSubject(models.Model):
    user  = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    group = models.ForeignKey(Group, on_delete=models.CASCADE)
    active = models.BooleanField(default=True)
    ts_start = models.DateTimeField(blank=True, null=True)
    ts_end = models.DateTimeField(blank=True, null=True)
class GroupResearcher(models.Model):
    user  = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    group = models.ForeignKey(Group, on_delete=models.CASCADE)
    active = models.BooleanField(default=True)
    ts_start = models.DateTimeField(blank=True, null=True)
    ts_end = models.DateTimeField(blank=True, null=True)




class SurveyDevice(Device):
    # epheremal surveys do not always have a token
    token        = models.CharField(max_length=32, null=True, blank=True,
                              help_text="The survey token, or blank for ephemeral surveys")
    persistent   = models.BooleanField(blank=True, default=True,
                              help_text="Does this survey have different tokens for each taking?")
    survey_active= models.BooleanField(blank=True, default=True,
                              help_text="Will this survey send notifications?")
    pyclass      = models.CharField(max_length=128, blank=True)
    pyclass_data = models.CharField(max_length=256, blank=True)
    send_via     = models.CharField(max_length=128, blank=True,
                              help_text="How to send survey to person?")


class SurveyToken(models.Model):
    token = models.CharField(max_length=32, primary_key=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL)
    #device = models.ForeignKey(SurveyDevice)
    device_id = models.CharField(max_length=64, unique=True)
    persistent= models.BooleanField(blank=True, default=True)
    # We have a lot of different timestamps:
    # - create:      when this row was created
    # - take:        when this can first be taken
    # - expire:      when one can no longer take this survey
    # - access:      when someone loads the page
    # - submit:      when someone submits the page
    # - notify_at:   when you should email the person
    # - notify_sent: when the notification was sent
    ts_create = models.DateTimeField(auto_now_add=True)
    #ts_take   = models.DateTimeField(blank=True, null=True)
    ts_expire = models.DateTimeField(blank=True, null=True)
    ts_access = models.DateTimeField(blank=True, null=True)
    ts_submit = models.DateTimeField(blank=True, null=True)
    #ts_notify_at   = models.DateTimeField(blank=True, null=True)
    #ts_notify_sent = models.DateTimeField(blank=True, null=True)
    data = models.CharField(max_length=256, blank=True)
    #admin_note = models.TextField(null=True, blank=True)
