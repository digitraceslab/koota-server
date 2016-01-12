from django.core.urlresolvers import reverse
from . import views as kviews
from . import models

import logging
log = logging.getLogger(__name__)

class KdataMiddleware(object):
    def process_view(self, request, view_func, args, kwargs):

        if kwargs.get('device_id', None):
            request.breadcrumbs = breadcrumbs = [ ]

            device_id = kwargs['device_id']
            breadcrumbs.append(('All Devices', reverse('device-list')))

            device = models.Device.objects.get(device_id=device_id)
            breadcrumbs.append((device.name, reverse('device', kwargs={'device_id':device_id})))
            #import IPython ; IPython.embed()
            if 'converter' in kwargs:
                breadcrumbs.append((kwargs['converter'], reverse('device-data',
                                                                 kwargs=dict(device_id=device_id,
                                                                             converter=kwargs['converter']))))
