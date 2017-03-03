from django.apps import AppConfig
from django.conf import settings

class KdataConfig(AppConfig):
    name = 'kdata'

    # This is the post-setup hook of an app.  Any extra devices to
    # register should be defined here.  We have the REGISTER_DEVICES
    # setting to do this.
    def ready(self):
        from .devices import base
        from . import util
        if hasattr(settings, 'REGISTER_DEVICES'):
            for row in settings.REGISTER_DEVICES:
                row['cls'] = util.import_by_name(row['cls'])
                base._register_device(**row)
