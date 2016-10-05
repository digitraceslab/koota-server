from django.contrib import admin

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
