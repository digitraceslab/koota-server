from django.core.urlresolvers import reverse
from . import views as kviews
from . import models
from . import group

import logging
log = logging.getLogger(__name__)

class KdataMiddleware(object):
    def process_view(self, request, view_func, args, kwargs):
        view_name = request.resolver_match.url_name

        request.breadcrumbs = breadcrumbs = [ ]
        breadcrumbs.append(('Koota', reverse('main')))

        # Group-related
        if view_func == group.group_join:
            breadcrumbs.append(('Groups', reverse('group-join')))
        if 'group_name' in kwargs:
            group_ = models.Group.objects.get(slug=kwargs['group_name'])
            breadcrumbs.append((group_.name,
                                reverse('group-detail',
                                        kwargs={'group_name':kwargs['group_name']})))
            if 'converter' in kwargs:
                breadcrumbs.append((kwargs['converter'],
                                    reverse('group-data',
                                            kwargs={'group_name':kwargs['group_name'],
                                                    'converter':kwargs['converter']})))
            if 'gs_id' in kwargs:
                groupsubject = models.GroupSubject.objects.get(id=kwargs['gs_id'])
                breadcrumbs.append((groupsubject.hash_if_needed(),
                                    None,
                                    reverse('group-subject-detail',
                                            kwargs=dict(group_name=kwargs['group_name'],
                                                        gs_id=kwargs['gs_id']))
                                            ))
                if 'public_id' in kwargs:
                    public_id = kwargs['public_id']
                    device = models.Device.get_by_id(public_id=public_id)
                    breadcrumbs.append(('%s (%s)'%(device.public_id, device.human_name()),
                                        None))
                    if view_name == 'group-subject-device-config':
                        breadcrumbs.append(('config',
                                            None))


        # Device-related
        elif kwargs.get('public_id', None):
            public_id = kwargs['public_id']
            breadcrumbs.append(('All Devices', reverse('device-list')))

            device = models.Device.get_by_id(public_id=public_id)
            breadcrumbs.append((device.name, reverse('device', kwargs={'public_id':public_id})))
            #import IPython ; IPython.embed()
            if 'converter' in kwargs:
                breadcrumbs.append((kwargs['converter'], reverse('device-data',
                                                                 kwargs=dict(public_id=public_id,
                                                                             converter=kwargs['converter']))))
        # Device list
        if view_name == 'device-list': #getattr(view_func, 'view_class', None) == kviews.DeviceListView:
            breadcrumbs.append(('All Devices', reverse('device-list')))

