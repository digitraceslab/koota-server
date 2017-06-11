import urllib

from django.contrib import messages
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.safestring import mark_safe

from . import views as kviews
from . import models
from . import group
from . import exceptions

import logging
log = logging.getLogger(__name__)

class KdataMiddleware(object):
    # The following two functions are for Django 1.10-style middleware
    # handling.  This is the default path, there is no actual code in
    # our class here.
    def __init__(self, get_response=None):
        self.get_response = get_response
    def __call__(self, request):
        response = self.get_response(request)
        return response


    def process_view(self, request, view_func, args, kwargs):
        view_name = request.resolver_match.url_name

        request.breadcrumbs = breadcrumbs = [ ]
        breadcrumbs.append(('Koota', reverse('main')))

        # Group-related
        if view_func == group.group_join:
            breadcrumbs.append(('Groups', reverse('group-join')))
        if 'group_name' in kwargs:
            breadcrumbs.append(('Groups', reverse('group-join')))
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
            if view_name == 'group-update':
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
            if view_name == 'device-config':
                breadcrumbs.append(('config',
                                        None))
        # Device list
        if view_name == 'device-list': #getattr(view_func, 'view_class', None) == kviews.DeviceListView:
            breadcrumbs.append(('All Devices', reverse('device-list')))



    def process_exception(self, request, exception):
        if isinstance(exception, exceptions.LoginRequired):
            querystring = urllib.parse.urlencode({'next':request.path})
            messages.warning(request, "Please log in to see this page (trace: %s)."%
                             exception.id_)
            return HttpResponseRedirect(reverse('login')+'?'+querystring,
                                        status=307, reason="Please log in")

        if isinstance(exception, exceptions.BaseMessageKootaException):
            response = TemplateResponse(request, 'koota/exception.html',
                                        context=dict(exception=exception),
                                        status=exception.status)
            response.reason_phrase = exception.message
            return response

