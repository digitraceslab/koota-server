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
admin.site.register(models.Device, DeviceAdmin)



class DataAdmin(admin.ModelAdmin):
    pass
admin.site.register(models.Data, DataAdmin)



class DeviceLabelAdmin(admin.ModelAdmin):
    pass
admin.site.register(models.DeviceLabel, DeviceLabelAdmin)



class GroupSubjectInline(admin.TabularInline):
    model = models.Group.subjects.through
class GroupResearcherInline(admin.TabularInline):
    model = models.Group.researchers.through
class GroupAdmin(admin.ModelAdmin):
    filter_horizontal = ('subjects', 'researchers')
    list_display = ['name', 'n_subjects', 'n_researchers', 'pyclass', 'otp_required', 'active']
    inlines = [
        GroupSubjectInline,
        GroupResearcherInline,
        ]
admin.site.register(models.Group, GroupAdmin)



class SurveyDeviceAdmin(admin.ModelAdmin):
    pass
admin.site.register(models.SurveyDevice, SurveyDeviceAdmin)
class SurveyTokenAdmin(admin.ModelAdmin):
    pass
admin.site.register(models.SurveyToken, SurveyTokenAdmin)
