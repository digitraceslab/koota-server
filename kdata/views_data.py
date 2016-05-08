from datetime import datetime

from django.shortcuts import render
from django.core.exceptions import PermissionDenied
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
logger = logging.getLogger(__name__)

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
            raise PermissionDenied("No permission for device")
        return device
    def get_context_data(self, **kwargs):
        """Override template context data with special instructions from the DeviceType object."""
        context = super(DeviceDetail, self).get_context_data(**kwargs)
        device_class = context['device_class'] = self.object.get_class()
        context.update(device_class.configure(device=self.object))
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
                                widget=forms.TextInput(attrs=dict(size=20)),
                                error_messages={'invalid':'Enter a valid start date/time, YYYY-MM-DD [HH:MM[:SS]].'})
    end = forms.DateTimeField(label="End time", required=False,
                                widget=forms.TextInput(attrs=dict(size=20)),
                                error_messages={'invalid':'Enter a valid end date/time, YYYY-MM-DD [HH:MM[:SS]].'})
    reversed = forms.BooleanField(label='reversed', initial=False, required=False)
def replace_page(request, n):
    """Manipulate query parameters: replace &page= with a new value.

    This is used for pagination while preserving the rest of the query
    parameters.

    """
    dict_ = request.GET.copy()
    dict_['page'] = n
    if n is None:
        del dict_['page']
    for key in list(dict_):
        if not dict_[key]:  del dict_[key]
    return dict_.urlencode()

def device_data(request, public_id, converter, format):
    """List data from one device+converter on a """
    context = c = { }
    # Get devices and other data
    device = c['device'] = models.Device.get_by_id(public_id=public_id)
    if not util.has_device_perm(request, device):
        raise PermissionDenied("No permission for device")
    device_class = c['device_class'] = device.get_class()
    converter_class = c['converter_class'] = \
        [ x for x in device_class.converters if x.name() == converter ][0]
    c['query_params_nopage'] = replace_page(request, '')

    # Fetch all relevant data
    queryset = models.Data.objects.filter(device_id=device.device_id, ).order_by('ts')
    if hasattr(converter_class, 'query'):
        queryset = converter_class.query(queryset)

    # Process the form and apply options
    form = c['select_form'] = DataListForm(request.GET)
    if form.is_valid():
        if form.cleaned_data['start']:
            queryset = queryset.filter(ts__gte=form.cleaned_data['start'])
        if form.cleaned_data['end']:
            queryset = queryset.filter(ts__lte=form.cleaned_data['end'])
        if form.cleaned_data['reversed']:
            queryset = queryset.reverse()
    else:
        # Bad data, return early and make the user fix the form
        return TemplateResponse(request, 'koota/device_data.html', context)

    # Paginate, if needed
    if converter_class.per_page is not None and not format:
        page_number = request.GET.get('page', 'last')
        paginator = Paginator(queryset, min(int(request.GET.get('perpage', converter_class.per_page)), 100))
        c['pages_total'] = paginator.num_pages
        if page_number == 'last':
            page_number = paginator.num_pages
        elif page_number:
            page_number = int(page_number)
            if int(page_number) > paginator.num_pages:
                # Page is out of bounds.  This can happen if someone
                # adjusts the date filters and , now there are fewer
                # pages and we are too far forward.  Redirect to same
                # URL with no page given.  Alternative solution: when
                # applying new filters, remove the page number?  Would
                # need to remove page from the filter form.
                return HttpResponseRedirect('?'+replace_page(request, n=None),
                                            reason='Page out of bounds')
        else:
            page_number = paginator.num_pages
        c['page_number'] = page_number
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
    else:
        # not paginating data
        data = queryset

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

    data = util.optimized_queryset_iterator(data)
    # Make our table object by passing raw data through the converter.
    catch_errors = 1
    if catch_errors:
        converter = c['converter'] \
                = converter_class(((x.ts, x.data) for x in data),
                                  time=time_converter)
        table = c['table'] = \
                converter.run()
    else:
        converter = c['converter'] = converter_class()
        table = c['table'] = converter.convert(((x.ts, x.data) for x in data),
                                               time=time_converter)

    # the "data" and "queryset" options are dangerous.  If they are
    # iterated throguh or maybe formatted by an error message, then we
    # get large memory consumption.
    del data, queryset

    # Convert to custom formats if it was requested.
    context['download_formats'] = [('csv2',  'csv (download)'),
                                   ('csv',   'csv (in browser)'),
                                   ('json2', 'json (dl)'),
                                   ('json',  'json (browser)'),
                                   ('json-lines2', 'json, in lines (dl)'),
                                   ('json-lines',  'json, in lines (browser)'),
                                  ]
    filename_base = '%s_%s_%s_%s-%s'%(
        device.public_id,
        device.type,
        converter.name(),
        form.cleaned_data['start'].strftime('%Y-%m-%d-%H:%M:%S') if form.cleaned_data['start'] else '',
        form.cleaned_data['end'].strftime('%Y-%m-%d-%H:%M:%S') if form.cleaned_data['end'] else ''
    )
    if format:
        return handle_format_downloads(table,
                                       format,
                                       converter=converter,
                                       header=converter.header2(),
                                       filename_base=filename_base,
                                       )

    # Done, return
    return TemplateResponse(request, 'koota/device_data.html', context)



def handle_format_downloads(table, format, converter, header, filename_base):
    if format and format.startswith('csv-aligned'):
        lines = util.csv_aligned_iter(table, converter=converter, header=header)
        response = StreamingHttpResponse(lines, content_type='text/plain')
        # Force download for the '2' options.
        if format.endswith('2'):
            filename = filename_base+'.csv'
            response['Content-Disposition'] = 'attachment; filename="%s"'%filename
        return response
    elif format and format.startswith('csv'):
        lines = util.csv_iter(table, converter=converter, header=header)
        response = StreamingHttpResponse(lines, content_type='text/plain')
        # Force download for the '2' options.
        if format.endswith('2'):
            filename = filename_base+'.csv'
            response['Content-Disposition'] = 'attachment; filename="%s"'%filename
        return response
    # A JSON format where there is one object on every line
    elif format and format.startswith('json-lines'):
        print('x'*50)
        lines = util.json_lines_iter(table, converter=converter)
        response = StreamingHttpResponse(lines, content_type='text/plain')
        # Force download for the '2' options.
        if format.endswith('2'):
            filename = filename_base+'.json-lines'
            response['Content-Disposition'] = 'attachment; filename="%s"'%filename
        return response
    elif format and format.startswith('json'):
        lines = util.json_iter(table, converter=converter)
        response = StreamingHttpResponse(lines, content_type='text/plain')
        # Force download for the '2' options.
        if format.endswith('2'):
            filename = filename_base+'.json'
            response['Content-Disposition'] = 'attachment; filename="%s"'%filename
        return response
    else:
        raise ValueError("Unknown format: %s"%format)
