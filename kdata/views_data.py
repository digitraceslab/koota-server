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
from json import dumps, loads
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
        device = self.model.get_by_id(public_id=self.kwargs['public_id'])
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
        device_data = models.Data.objects.filter(device_id=self.object.device_id)
        context['data_number'] = device_data.count()
        if context['data_number'] > 0:
            context['data_earliest'] = device_data.order_by('ts').first().ts
            context['data_latest'] = device_data.order_by('-ts').first().ts
            context['data_latest_data'] = device_data.order_by('-ts').first().data

        return context


class IntegerOrLastField(forms.IntegerField):
    """An integer field that also accepts the value 'last'.

    This is used as an input field for pagination, accepting a value
    that goes to the last page.
    """
    def to_python(self, value):
        if value == 'last': return value
        return super(forms.IntegerField, self).to_python(value)
class DataListForm(forms.Form):
    """Form to query and page through submitted data."""
    page = IntegerOrLastField(label='page', required=False, widget=forms.HiddenInput)
    start = forms.DateTimeField(label="Start time", required=False,
                                widget=forms.TextInput(attrs=dict(size=20)))
    end = forms.DateTimeField(label="End time", required=False,
                                widget=forms.TextInput(attrs=dict(size=20)))
    reversed = forms.BooleanField(label='reversed', initial=False, required=False)
def replace_page(request, n):
    """Manipulate query parameters: replace &page= with a new value.

    This is used for pagination while preserving the rest of the query
    parameters.

    """
    dict_ = request.GET.copy()
    dict_['page'] = n
    for key in list(dict_):
        if not dict_[key]:  del dict_[key]
    return dict_.urlencode()

def device_data(request, public_id, converter, format):
    """List data from one device+converter on a """
    context = c = { }
    # Get devices and other data
    device = c['device'] = models.Device.get_by_id(public_id=public_id)
    if not util.has_device_perm(request, device):
        return HttpResponse(status=403, reason='Not authorized')
    device_class = c['device_class'] = devices.get_class(device.type)
    converter = c['converter'] = \
        [ x for x in device_class.converters if x.name() == converter ][0]
    c['query_params_nopage'] = replace_page(request, '')

    # Fetch all relevant data
    queryset = models.Data.objects.filter(device_id=device.device_id, ).order_by('ts').defer('data')

    # Process the form and apply options
    form = c['select_form'] = DataListForm(request.GET)
    if form.is_valid():
        if form.cleaned_data['start']:
            queryset = queryset.filter(ts__gte=form.cleaned_data['start'])
        if form.cleaned_data['end']:
            queryset = queryset.filter(ts__lte=form.cleaned_data['end'])
        if form.cleaned_data['reversed']:
            queryset = queryset.reverse()
    data = queryset

    # Paginate, if needed
    if converter.per_page is not None and not format:
        page_number = c['page_number'] = request.GET.get('page', None)
        paginator = Paginator(queryset, min(int(request.GET.get('perpage', converter.per_page)), 100))
        c['pages_total'] = paginator.num_pages
        if page_number == 'last':
            page_number = paginator.num_pages
        elif page_number:
            page_number = int(page_number)
        else:
            page_number = 1
        page_obj = c['page_obj'] = paginator.page(page_number)
        # Set our URLs for pagination.  Need to do this here because
        # you can't embed tags within filter arguments, at least so I
        # see.
        if page_number > 1:   c['page_first'] = replace_page(request, 1)
        if page_obj.has_previous(): c['page_prev']  = replace_page(request, page_number-1)
        if page_obj.has_next(): c['page_next']  = replace_page(request, page_number+1)
        if page_number < paginator.num_pages:
                              c['page_last']  = replace_page(request, 'last')
        data = page_obj.object_list

    # For web view, convert to pretty time, others use raw unixtime.
    if not format or request.GET.get('textdate', False):
        #from django.utils import timezone as timezone
        # There is no way to get the browser's timezone automatically
        # (not sent in the request), so we can't use
        # django.utils.timezone to make things automatic.  If we had
        # the proper timezone, we would use the activate() function in
        # there and possible also localtime() there, and we would
        # convert to the user's tz.  Of course, maybe it's better to
        # not do this with django, but just manually do it here.
        time_converter = lambda ts: datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
    else:
        time_converter = lambda ts: ts

    # Make our table object by passing raw data through the converter.
    table = c['table'] = \
      converter().convert(((x.ts, x.data) for x in data.iterator()),
                          time=time_converter)

    # Convert to custom formats if it was requested.
    context['download_formats'] = [('csv2',  'csv (download)'),
                                   ('json2', 'json (download)'),
                                   ('csv',   'csv (in browser)'),
                                   ('json',  'json (in browser)'),
                                  ]
    if format and format.startswith('csv'):
        import csv
        from six import StringIO as IO
        def csv_iter():
            rows = iter(table)
            fo = IO()
            csv_writer = csv.writer(fo)
            csv_writer.writerow(converter.header2())
            while True:
                try:
                  for _ in range(1000):
                    row = next(rows)
                    #print row
                    csv_writer.writerow(row)
                except StopIteration:
                    fo.seek(0)
                    yield fo.read().encode('utf-8')
                    del fo
                    break
                fo.seek(0)
                data = fo.read().encode('utf-8')
                fo.seek(0)
                fo.truncate()
                yield data
        response = StreamingHttpResponse(csv_iter(), content_type='text/plain')
        # Force download for the '2' options.
        if format.endswith('2'):
            filename = '%s_%s_%s_%s-%s.%s'%(device.public_id,
                                            device.type,
                                            converter.name(),
                                            form.cleaned_data['start'].strftime('%Y-%m-%d-%H:%M:%S') if form.cleaned_data['start'] else '',
                                            form.cleaned_data['end'].strftime('%Y-%m-%d-%H:%M:%S') if form.cleaned_data['end'] else '',
                                            'csv')
            response['Content-Disposition'] = 'attachment; filename="%s"'%filename
        return response
    elif format and format.startswith('json'):
        def json_iter():
            rows = iter(table)
            yield '[\n'
            try:
                yield dumps(next(rows))  # first one (hope there is no StopIteration now)
                while True:
                    row = next(rows)  # raises StopIteration if data exhausted
                    yield ',\n'  # finalize the one from before, IF we have a next row
                    yield dumps(row)
            except StopIteration:
                pass
            yield '\n]'
        response = StreamingHttpResponse(json_iter(), content_type='text/plain')
        # Force download for the '2' options.
        if format.endswith('2'):
            filename = '%s_%s_%s_%s-%s.%s'%(device.public_id,
                                            device.type,
                                            converter.name(),
                                            form.cleaned_data['start'].strftime('%Y-%m-%d-%H:%M:%S') if form.cleaned_data['start'] else '',
                                            form.cleaned_data['end'].strftime('%Y-%m-%d-%H:%M:%S') if form.cleaned_data['end'] else '',
                                            'json')
            response['Content-Disposition'] = 'attachment; filename="%s"'%filename
        return response


    # Done, return
    return TemplateResponse(request, 'koota/device_data.html', context)


def download_data(request, public_id):
    #if not util.has_device_perm(request, public_id):
    #    raise Http404
    objects = models.Data.objects.filter(public_id=public_id, ).order_by('ts')
    def streamer():
        yield '{ "data": [ \n'
        for obj in objects:
            yield json.dumps(obj.data)
            yield ', \n'
        yield ']}'
    return StreamingHttpResponse(streamer())
    #return HttpResponse(''.join(streamer()))
