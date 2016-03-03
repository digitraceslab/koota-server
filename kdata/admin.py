from django.contrib import admin

# Register your models here.

from . import models

class DeviceAdmin(admin.ModelAdmin):
    list_display = ('device_id', 'user', 'name', 'type', 'active')
admin.site.register(models.Device, DeviceAdmin)
class DataAdmin(admin.ModelAdmin):
    pass
admin.site.register(models.Data, DataAdmin)
class DeviceLabelAdmin(admin.ModelAdmin):
    pass
admin.site.register(models.DeviceLabel, DeviceLabelAdmin)
