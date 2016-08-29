from __future__ import unicode_literals

from django.contrib.auth.models import User
from django.conf import settings
from django.db import models
from django.utils import timezone

from . import devices
from . import exceptions
from . import util
# Create your models here.

import logging
logger = logging.getLogger(__name__)

class Data(models.Model):
    class Meta:
        index_together = [
            ["device_id", "ts"],
            ]
    id = models.AutoField(primary_key=True)
    device_id = models.CharField(max_length=64)
    ts = models.DateTimeField(auto_now_add=True,
                              help_text="Time the data referrs to, defaults to received timestamp.")
    # Column is nullable since it is added later, remove null=True
    # later.
    ts_received = models.DateTimeField(auto_now_add=True, null=True,
                                       help_text="Time packet received (never updated)")
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

    def __init__(self, *args, **kwargs):
        super(Device, self).__init__(*args, **kwargs)
        # Set up dict-like object for accessing key-value attributes
        self.attrs = AttrInterface(self.deviceattr_set)
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
            raise exceptions.NoDevicePermission(log="device ID too short")
        return cls.objects.get(_public_id=public_id)
    @classmethod
    def get_by_id_insecure(cls, public_id):
        """Only for use in admin scripts"""
        return cls.objects.get(_public_id=public_id)
    @classmethod
    def get_by_secret_id(cls, secret_id):
        if len(secret_id) < 10:
            raise exceptions.InvalidDeviceID(log="device ID too short")
        return cls.objects.get(_secret_id=secret_id)
    def get_class(self):
        """Return the Python class corresponding to this device."""
        cls = devices.get_class(self.type)
        return cls(self)
    def human_name(self):
        # We have to import the class here to make sure that the
        # device is registered.
        if self.type not in devices.device_class_lookup:
            self.get_class()
        # djnago's internal "human name" functionality.
        return self.get_type_display()
# See comment in kdata.devices.register_device to know why this is
# here. It is a hack to work around a circular import.
Device._meta.get_field('type').choices = devices.all_device_choices



class BaseAttr(models.Model):
    """Arbitrary attributes for objects"""
    class Meta:
        abstract = True
        index_together = [
            ("device", "name"),
            ("name", "value"),
            ]
        unique_together = [
            ("device", "name"),
            ]
    #device = models.ForeignKey(Device)
    name = models.CharField(max_length=64,
                            help_text='Attribute name')
    value = models.CharField(max_length=128,
                            help_text='Attribute value')
    ts = models.DateTimeField(auto_now=True)


class DeviceAttr(BaseAttr):
    device = models.ForeignKey(Device)



class AttrInterface(object):
    """Dictionary-like interface to DeviceAttr (and others)

    This provides a dictionary-like interface to device attributes
    (and others).  This allows arbitrary metadata on each device
    object.  This is initialized in the __init__ method of each object
    (like Device.__init__).
    """
    def __init__(self, attrset):
        self.attrset = attrset
    def __contains__(self, name):
        return self.attrset.filter(name=name).exists()
    def __getitem__(self, name):
        qs = self.attrset.filter(name=name)
        if qs.exists():
            return qs.get().value
        raise KeyError("Device does not have attr %s"%(name))
    def get(self, name, default=None):
        qs = self.attrset.filter(name=name)
        if qs.exists():
            return qs.get().value
        return default
    def __setitem__(self, name, value):
        qs = self.attrset.filter(name=name)
        if qs.exists():
            return qs.update(value=value, ts=timezone.now())
        return self.attrset.create(name=name, value=value)
    def __delitem__(self, name):
        return self.attrset.filter(name=name).delete()
    def items(self):
        return self.attrset.values_list('name', 'value')



class DeviceLabel(models.Model):
    name        = models.CharField(max_length=64, blank=True)
    shortname   = models.CharField(max_length=64, blank=True)
    description = models.CharField(max_length=256,blank=True)
    slug        = models.CharField(max_length=64, blank=True,
                                   unique=True, db_index=True,
                                   help_text="slug for querying")
    analyze     = models.BooleanField(help_text="Include this label in analysis?",
                                      default=False)
    order       = models.IntegerField(default=0, help_text="Order in UI.")
    def __str__(self):
        return self.name



class Group(models.Model):
    def __init__(self, *args, **kwargs):
        super(Group, self).__init__(*args, **kwargs)
        # Set up dict-like object for accessing key-value attributes
        self.attrs = AttrInterface(self.groupattr_set)
    slug = models.CharField(max_length=64, unique=True,
                      help_text="Short unique identifier, no spaces.")
    name = models.CharField(max_length=64,
                      help_text="Name of study, for humans.")
    desc = models.CharField(max_length=64,
                      help_text="Short description (64 chars)")
    desc_long = models.TextField(blank=True,
                      help_text="Long description explaining study.  Include contact info.")
    invite_code = models.CharField(max_length=64, blank=True,
                      help_text="Invite code, for subjects to join.")
    pyclass = models.CharField(max_length=128, blank=True,
                      help_text="Python class which manages this object.")
    pyclass_data = models.CharField(max_length=256, blank=True,
                      help_text="Configuration data for Python class.")
    url = models.CharField(max_length=256, blank=True,
                      help_text="URL with more study information.")
    url_privacy = models.CharField(max_length=256, blank=True,
                      help_text="URL with study privacy information.")
    ts_start = models.DateTimeField(blank=True, null=True,
                      help_text="Timestamp start, data available after this time.")
    ts_end = models.DateTimeField(blank=True, null=True,
                      help_text="Timestamp end, data available before this time.")
    # Properties
    active = models.BooleanField(default=True,
                      help_text="Is this study available for joining and active?")
    archived = models.BooleanField(default=False,
                      help_text="Is this study archived?")
    otp_required = models.BooleanField(default=False,
                      help_text="Require 2FA for researchers?")
    nonanonymous = models.BooleanField(default=False,
                      help_text="If true, usernames and device IDs, and individual device data will be visible to researchers")
    managed = models.BooleanField(default=False,
                      help_text="If true, managers will be able to control devices.")
    leaveable = models.BooleanField(default=False,
                      help_text="Can subjects can leave this study by themselves?")
    #
    salt = models.CharField(max_length=128,
                            default=util.random_salt_b64, blank=True,
                      help_text="A hash salt for this group")
    priority = models.IntegerField(default=0,
                      help_text=("In what order should group configuration "
                                 "be applied?  higher=more priority"))
    config = util.JsonConfigField(blank=True,
                      help_text="Arbitrary JSON configuration for this group.")
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
        """Is given user a researcher of this group?

        All researchers are researchers by default, unless their
        researcher attribute is false.
        """
        gr = GroupResearcher.objects.filter(group=self,
                                            user=user)
        # Must have a GroupResearcher entry.
        if not gr.exists(): return False
        # Everyone is researcher by default, but if
        # GroupResearcher.reseacher is false, then they are not
        # researcher.  Default (=None), they are a researcher.
        if gr.get().researcher is False: return False
        return True
    def is_manager(self, user):
        """Is given user a manager of this group?

        Manager condition: group managed, researcher has manager tag."""
        # If group is not managed, always deny.
        if not self.managed: return False
        # Must have GroupResearcher entry, and .manager must be true.
        gr = GroupResearcher.objects.filter(group=self,
                                            user=user)
        if not gr.exists(): return False
        if not gr.get().manager: return False
        return True
    def is_admin(self, user):
        """Is given user a admin.

        Admin conditions: group managed, researcher has admin tag."""
        # If group is not managed, always deny.
        if not self.managed: return False
        gr = GroupResearcher.objects.filter(group=self,
                                            user=user)
        # We must have GroupResearcher entry, and .admin must be True.
        if not gr.exists(): return False
        if not gr.get().admin: return False
        return True



class GroupAttr(BaseAttr):
    # This is wrong, but called "device".  This is to save code by
    # using the abstract base class BaseAttr and sharing with the
    # DeviceAttr which came first.
    device = models.ForeignKey(Group, on_delete=models.CASCADE)



class GroupSubject(models.Model):
    user  = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    group = models.ForeignKey(Group, on_delete=models.CASCADE)
    active = models.BooleanField(default=True)
    ts_start = models.DateTimeField(blank=True, null=True)
    ts_end = models.DateTimeField(blank=True, null=True)
    notes = models.TextField(blank=True)
    #nonanonymous = NullBoolean
    def __str__(self):
        return '<GroupSubject(%s, %s)>'%(repr(self.hash_if_needed()),
                                         repr(self.group.slug))
    def hash(self):
        # TODO: duplicated in iter_group_data.
        return util.safe_hash(self.group.salt+self.user.username)
    def hash_if_needed(self):
        """Subject ID, hashed if necessary"""
        if self.group.nonanonymous:
            return self.user.username
        else:
            return util.safe_hash(self.group.salt+self.user.username)
class GroupResearcher(models.Model):
    user  = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    group = models.ForeignKey(Group, on_delete=models.CASCADE)
    active = models.BooleanField(default=True)
    ts_start = models.DateTimeField(blank=True, null=True)
    ts_end = models.DateTimeField(blank=True, null=True)
    researcher = models.NullBooleanField(blank=True, null=True, default=None,
                                         help_text="Has access to data?")
    manager = models.NullBooleanField(blank=True, null=True, default=False,
                                      help_text="Has access to manage users?")
    admin = models.NullBooleanField(blank=True, null=True, default=False,
                                    help_text="Has access to adjust group properties?")
    def __str__(self):
        return '<GroupResearcher(%s, %s)>'%(self.user.username, self.group.slug)




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



class OauthDevice(Device):
    # service     # Which service is this: twitter, facebook, etc.
                  # specifies consumer keys
    service          = models.CharField(max_length=64, blank=True)
    # state       # unlinked, requested, linked, expired, invalid
    state            = models.CharField(max_length=16, blank=True)
    # data for any error
    error            = models.CharField(max_length=256, blank=True)
    # Any free-form text that may need to be associated with this.
    data             = models.CharField(max_length=265, blank=True)
    request_key      = models.CharField(max_length=256, blank=True, db_index=True)
    request_secret   = models.CharField(max_length=256, blank=True)
    resource_key     = models.CharField(max_length=256, blank=True)
    resource_secret  = models.CharField(max_length=256, blank=True)
    refresh_token    = models.CharField(max_length=256, blank=True)
    ts_create        = models.DateTimeField(auto_now_add=True)
    # ts_linked   # When initial linking was done
    ts_linked        = models.DateTimeField(null=True, blank=True)
    # Last fetch of data
    ts_last_fetch    = models.DateTimeField(null=True, blank=True)
    # When token must be refreshed
    ts_refresh       = models.DateTimeField(null=True, blank=True)
    # When refresh token must be refreshed
    ts_refresh2      = models.DateTimeField(null=True, blank=True)



# To set a password:
#   import kdata.models
#   u = kdata.models.MosquittoUser.objects.get(username='ramcli')
#   u.passwd = 'test'
#   u.save()
class MosquittoUser(models.Model):
    """Mosquetto usernames/passwords.

    This is used for MQTT users, but *not* for normal devices - those
    are in device attributes.
    """
    username = models.CharField(max_length=64, unique=True)
    _passwd = models.CharField(db_column='passwd', max_length=256,
                              help_text="hashed password")
    superuser = models.BooleanField(default=False,
                                    help_text="Is a superuser?")
    @property
    def passwd(self):
        return self._passwd
    @passwd.setter
    def passwd(self, passwd):
        passwd = util.hash_mosquitto_password(passwd)
        self._passwd = passwd
class MosquittoAcl(models.Model):
    user = models.ForeignKey(MosquittoUser, on_delete=models.CASCADE)
    topic = models.CharField(max_length=256, db_index=True,
                             help_text="mosquitto topic filter, including + and #.")
    rw = models.IntegerField(default=1,
                             help_text="1=ro, 2=rw")



# These at bottom to avoid circular import problems
from . import group
