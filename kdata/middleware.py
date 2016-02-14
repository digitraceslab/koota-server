from django.core.urlresolvers import reverse
from . import views as kviews
from . import models

import logging
log = logging.getLogger(__name__)

class KdataMiddleware(object):
    def process_view(self, request, view_func, args, kwargs):
        request.breadcrumbs = breadcrumbs = [ ]
        breadcrumbs.append(('Koota', reverse('main')))

        if kwargs.get('public_id', None):

            public_id = kwargs['public_id']
            breadcrumbs.append(('All Devices', reverse('device-list')))

            device = models.Device.get_by_id(public_id=public_id)
            breadcrumbs.append((device.name, reverse('device', kwargs={'public_id':public_id})))
            #import IPython ; IPython.embed()
            if 'converter' in kwargs:
                breadcrumbs.append((kwargs['converter'], reverse('device-data',
                                                                 kwargs=dict(public_id=public_id,
                                                                             converter=kwargs['converter']))))
        if getattr(view_func, 'view_class', None) == kviews.DeviceListView:
            breadcrumbs.append(('All Devices', reverse('device-list')))
