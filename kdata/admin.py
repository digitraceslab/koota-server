from django.contrib import admin

from django.conf import settings

# Register your models here.

from . import models

class DeviceAttrInline(admin.TabularInline):
    model = models.DeviceAttr
class DeviceAdmin(admin.ModelAdmin):
    list_display = ('device_id', 'user', 'name', 'type', 'active')
    inlines = [
        DeviceAttrInline,
        ]
    search_fields = ('_public_id', 'device_id', '_secret_id', 'user__username', )
admin.site.register(models.Device, DeviceAdmin)



class DataAdmin(admin.ModelAdmin):
    pass
admin.site.register(models.Data, DataAdmin)



class DeviceLabelAdmin(admin.ModelAdmin):
    list_display = ('name', 'id', 'shortname', 'description', 'slug', 'analyze', 'order')
    pass
admin.site.register(models.DeviceLabel, DeviceLabelAdmin)



class GroupSubjectInline(admin.TabularInline):
    model = models.Group.subjects.through
class GroupResearcherInline(admin.TabularInline):
    model = models.Group.researchers.through
class GroupAttrInline(admin.TabularInline):
    model = models.GroupAttr
class GroupAdmin(admin.ModelAdmin):
    filter_horizontal = ('subjects', 'researchers')
    list_display = ['name', 'priority', 'n_subjects', 'n_researchers', 'pyclass', 'managed', 'nonanonymous', 'otp_required', 'active', 'ts_start', 'ts_end']
    inlines = [
        GroupAttrInline,
        GroupSubjectInline,
        GroupResearcherInline,
        ]
    search_fields = ('slug', 'name', 'invite_code', 'pyclass')
admin.site.register(models.Group, GroupAdmin)



class SurveyDeviceAdmin(admin.ModelAdmin):
    pass
admin.site.register(models.SurveyDevice, SurveyDeviceAdmin)
class SurveyTokenAdmin(admin.ModelAdmin):
    pass
admin.site.register(models.SurveyToken, SurveyTokenAdmin)


# For Mosquitto authentication.
class MosquittoAclInline(admin.TabularInline):
    model = models.MosquittoAcl
class MosquittoUserAdmin(admin.ModelAdmin):
    list_display = ['username', 'superuser']
    inlines = [
        MosquittoAclInline
        ]
admin.site.register(models.MosquittoUser, MosquittoUserAdmin)


class ConsentAdmin(admin.ModelAdmin):
    list_display = ['user', 'group', 'sha256']
admin.site.register(models.Consent, ConsentAdmin)



# The following overrides and changes the default django.contrib.auth
# UserModel so that it will show our devices and groups info.  We add
# the same information as we see from groups (what groups this user is
# in as a subject and researcher), and what devices this user owns.
import django.contrib.auth
from django.contrib.auth.admin import UserAdmin
User = django.contrib.auth.get_user_model()
class UserGroupSubjectInline(admin.TabularInline):
    model = User.subject_of_groups.through
class UserGroupResearcherInline(admin.TabularInline):
    model = User.researcher_of_groups.through
class UserDevices(admin.TabularInline):
    model = models.Device
class UserAdmin(UserAdmin):
    #filter_horizontal = ('subjects', 'researchers')
    list_display = ['username', ]
    inlines = [
        UserGroupSubjectInline,
        UserGroupResearcherInline,
        UserDevices,
        ]
    search_fields = ('username', 'email')
# https://stackoverflow.com/a/10956717
admin.site.unregister(django.contrib.auth.get_user_model())
admin.site.register(django.contrib.auth.get_user_model(), UserAdmin)
