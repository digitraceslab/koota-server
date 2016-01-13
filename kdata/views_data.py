from datetime import datetime

from django.shortcuts import render
from django.core.paginator import InvalidPage, Paginator
from django.core.urlresolvers import reverse
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect, Http404
from django.http import StreamingHttpResponse
from django.template.response import TemplateResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import ListView, DetailView, CreateView, UpdateView, FormView

import json
import time
from . import models
from . import devices
from . import util

import logging
log = logging.getLogger(__name__)

from django import forms
from django.contrib.auth.models import User
import django.contrib.auth as auth


class DeviceDetail(DetailView):
    """List metadata about the device and its data
    """
    template_name = 'koota/device_detail.html'
    model = models.Device
    def get_object(self):
        """Get device model object, testing permissions"""
        device = self.model.objects.get(device_id=self.kwargs['device_id'])
        if not util.has_device_perm(self.request, device):
            raise Http404
        return device
    def get_context_data(self, **kwargs):
        """Override template context data with special instructions from the DeviceType object."""
        context = super(DeviceDetail, self).get_context_data(**kwargs)
        device_class = context['device_class'] = devices.get_class(self.object.type)
        try:
            context.update(device_class.configure(device=self.object))
        except devices.NoDeviceTypeError:
            pass
        device_data = models.Data.objects.filter(device_id=self.kwargs['device_id'])
        context['data_number'] = device_data.count()
        if context['data_number'] > 0:
            context['data_earliest'] = device_data.order_by('ts').first().ts
            context['data_latest'] = device_data.order_by('-ts').first().ts
            context['data_latest_data'] = device_data.order_by('-ts').first().data

        return context

def device_data(request, device_id, converter, format):
    """List data from one device+converter on a """
    context = c = { }
    # Get devices and other data
    device = models.Device.objects.get(device_id=device_id)
    if not util.has_device_perm(request, device):
        return HttpResponse(status=403, reason='Not authorized')
    device_class = c['device_class'] = devices.get_class(device.type)
    converter = c['converter'] = \
        [ x for x in device_class.converters if x.name() == converter ][0]

    # Fetch all relevant data
    queryset = models.Data.objects.filter(device_id=device_id, ).order_by('ts').defer('data')
    data = queryset

    # Paginate, if needed
    if converter.per_page is not None and not format:
        page_number = request.GET.get('page', None)
        paginator = Paginator(queryset, converter.per_page)
        if page_number == 'last':
            page_number = paginator.num_pages
        elif page_number:
            page_number = int(page_number)
        else:
            page_number = 1
        page_obj = c['page_obj'] = paginator.page(page_number)
        data = page_obj.object_list

    # For web view, convert to pretty time, others use raw unixtime.
    if not format:
        time_converter = lambda ts: datetime.fromtimestamp(ts)
    else:
        time_converter = lambda ts: ts

    # Make our table object by passing raw data through the converter.
    table = c['table'] = \
      converter().convert(((x.ts, x.data) for x in data.iterator()),
                          time=time_converter)

    # Convert to custom formats if it was requested.
    context['download_formats'] = ['csv']
    if format == 'csv':
        import csv
        import cStringIO
        def csv_iter():
            rows = iter(table)
            fo = cStringIO.StringIO()
            csv_writer = csv.writer(fo)
            csv_writer.writerow(converter.header)
            while True:
                try:
                  for _ in range(1000):
                    row = next(rows)
                    #print row
                    csv_writer.writerow(row)
                except StopIteration:
                    fo.seek(0)
                    yield fo.read()
                    del fo
                    break
                fo.seek(0)
                data = fo.read()
                fo.seek(0)
                fo.truncate()
                yield data
        response = StreamingHttpResponse(csv_iter(), content_type='text/plain')
        filename = '%s-%s-%s.%s'%(device_id[:6], device.type, time.strftime('%Y-%d-%d_%H:%M'), format)
        response['Content-Disposition'] = 'filename="foo.xls"'
        return response


    # Done, return
    return TemplateResponse(request, 'koota/device_data.html', context)


def download_data(request, device_id):
    #if not util.has_device_perm(request, device_id):
    #    raise Http404
    objects = models.Data.objects.filter(device_id=device_id, ).order_by('ts')
    def streamer():
        yield '{ "data": [ \n'
        for obj in objects:
            yield json.dumps(obj.data)
            yield ', \n'
        yield ']}'
    return StreamingHttpResponse(streamer())
    #return HttpResponse(''.join(streamer()))
