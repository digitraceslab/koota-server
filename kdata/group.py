from datetime import datetime
import itertools
import random

from django import forms
from django.core.exceptions import PermissionDenied
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.urlresolvers import reverse, reverse_lazy
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect, Http404
from django.http import StreamingHttpResponse
from django.views.generic import ListView, DetailView, CreateView, UpdateView, FormView
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _
from django.template.response import TemplateResponse

from . import converter
from . import devices
from . import models
from . import util
from . import views
from . import views_data

class JoinGroupForm(forms.Form):
    invite_code = forms.CharField()
    groups = forms.CharField(widget=forms.HiddenInput, required=False)
@login_required
def group_join(request):
    """View to present group invitations.

    This will:
    - Allow user to specify an invite code.
    - Confirm the groups that the user will join
    - Add user to those groups.
    """
    context = c = { }
    user = request.user
    if not user.is_authenticated():
        raise Http404 # should never get here, we have login_required
    if request.method == 'POST':
        form = JoinGroupForm(request.POST)
        if form.is_valid():
            invite_code = form.cleaned_data['invite_code']
            groups = models.Group.objects.filter(invite_code=invite_code)
            context['groups'] = groups
            groups_str = ','.join(sorted(g.name for g in groups))
            if groups_str == form.cleaned_data['groups']:
                # Second stage.  User was presented the groups on the
                # last round, so now do the actual addition.
                c['round'] = 'done'
                for group in groups:
                    #group.subjects.add(request.user)
                    if group.subjects.filter(id=user.id).exists():
                        continue
                    models.GroupSubject.objects.create(user=user, group=group)
                    print("added %s to %s"%(user, group))
            else:
                # First stage.  User entered invite code.  We have to
                # present the data again, so that user can verify the
                # group that they are joining.
                c['round'] = 'verify'
                form.data = form.data.copy()
                form.data['groups'] = groups_str
    else:
        # Initial, present box for invite code.
        c['round'] = 'initial'
        form = JoinGroupForm(initial=request.GET)
    c['form'] = form
    return TemplateResponse(request, 'koota/group_join.html',
                            context=context)


def group_view(request, group_name):
    context = c = { }
    group = models.Group.objects.get(slug=group_name)
    if not has_group_researcher_permission(group, request.user):
        raise PermissionDenied("No permission for device")
    group_class = group.get_class()
    G = group.get_class()
    c['group'] = group
    c['G'] = G
    # effective number of subjects: can be overridden
    c['n_subjects'] = sum(1 for _ in iter_subjects(group, group_class))
    return TemplateResponse(request, 'koota/group_view.html',
                            context=context)



def has_group_researcher_permission(group, user):
    group_class = group.get_class()
    if hasattr(group_class, 'is_researcher'):
        if group_class.is_researcher(user):
            return True
    else:
        if group.is_researcher(user):
            return True
    return False
def iter_subjects(group, group_class):
    """Iterate through all subjects in group"""
    if hasattr(group_class, 'subjects_iter'):
        subjects = group_class.subjects_iter()
    else:
        subjects = group.subjects.all()
    subjects = list(subjects)
    random.shuffle(subjects)
    for subject in subjects:
        yield subject
def iter_users_devices(group, group_class, group_converter_class):
    """Iterate (user, device_id) pairs in group"""
    for subject in iter_subjects(group, group_class):
        for device in models.Device.objects.filter(user=subject,
                                         type=group_converter_class.device_class,
                                         label__name='Primary personal device'):
            yield subject, device



def group_data(request, group_name, converter, format=None):
    context = c = { }
    group = models.Group.objects.get(slug=group_name)
    group_class = group.get_class()
    if not has_group_researcher_permission(group, request.user):
        raise PermissionDenied("No permission for device")

    # Process the form and apply options
    form = c['select_form'] = views_data.DataListForm(request.GET)
    if form.is_valid():
        pass
    else:
        # Bad data, return early and make the user fix the form
        return TemplateResponse(request, 'koota/device_data.html', context)
    c['query_params_nopage'] = views_data.replace_page(request, '')

    c['group'] = group
    c['group_class'] = group_class
    group_converter_class = [ x for x in group_class.converters
                              if x.name() == converter ][0]
    group_converter_class = get_group_converter(group_converter_class)
    group_converter_class = c['group_converter_class'] = group_converter_class

    converter_class = group_converter_class.converter
    converter_for_errors = converter_class(rows=None)

    def queryset_filter(queryset):
        """Callback to apply our queryset filtering operations."""
        #import IPython ; IPython.embed()
        if hasattr(converter_class, 'query'):
            queryset = converter_class.query(queryset)
        if group.ts_start: queryset = queryset.filter(ts__gte=group.ts_start)
        if group.ts_end:   queryset = queryset.filter(ts__lt=group.ts_end)
        if form.cleaned_data['start']:
            queryset = queryset.filter(ts__gte=form.cleaned_data['start'])
        if form.cleaned_data['end']:
            queryset = queryset.filter(ts__lte=form.cleaned_data['end'])
        if form.cleaned_data['reversed']:
            queryset = queryset.reverse()
        return queryset

    # For web view, convert to pretty time, others use raw unixtime.
    if not format or request.GET.get('textdate', False):
        time_converter = lambda ts: datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
    else:
        time_converter = lambda ts: ts


    def iter_data():
        """Core data iterator: (user, data, converter_data...)"""
        hash_subject = util.IntegerMap()
        hash_device  = util.IntegerMap()
        hash_subject = util.safe_hash
        hash_device  = util.safe_hash

        for subject, device in iter_users_devices(group, group_class, group_converter_class):
            subject_hash = hash_subject(subject.username)
            device_hash  = hash_device(device.public_id)

            # Fetch all relevant data
            queryset = models.Data.objects.filter(device_id=device.device_id, ).order_by('ts')
            queryset = queryset_filter(queryset)
            queryset = queryset.defer('data')

            rows = ((x.ts, x.data) for x in queryset.iterator())
            converter = converter_class(rows=rows, time=time_converter)
            converter.errors = converter_for_errors.errors
            converter.errors_dict = converter_for_errors.errors_dict
            rows = converter.run()
            if not format:
                rows = itertools.islice(rows, 50)
            #rows = converter.convert(rows=rows)
            for row in rows:
                yield (subject_hash, device_hash) + row

    table = iter_data()
    if not format:
        table = itertools.islice(table, 1000)
    c['table'] = table


    context['download_formats'] = [('csv2',  'csv (download)'),
                                   ('csv',   'csv (in browser)'),
                                   ('json2', 'json (dl)'),
                                   ('json',  'json (browser)'),
                                   ('json-lines2', 'json, in lines (dl)'),
                                   ('json-lines',  'json, in lines (browser)'),
                                  ]
    filename_base = '%s_%s_%s-%s'%(
        group.slug,
        converter_class.name(),
        form.cleaned_data['start'].strftime('%Y-%m-%d-%H:%M:%S') if form.cleaned_data['start'] else '',
        form.cleaned_data['end'].strftime('%Y-%m-%d-%H:%M:%S') if form.cleaned_data['end'] else '',
    )

    header = c['header'] = ['user', 'device', ] + converter_class.header2()

    if format:
        return views_data.handle_format_downloads(
            table,
            format,
            converter=converter_for_errors,
            header=header,
            filename_base=filename_base,
        )

    return TemplateResponse(request, 'koota/group_data.html',
                            context=context)


class _GroupConverter(object):
    pass
    @classmethod
    def name(cls):
        return cls.__name__
    desc = 'Base converter'
    converter = None
    device_class = None
def get_group_converter(obj):
    if issubclass(obj, converter._Converter):
        attrs = {
            'desc': obj.desc,
            'converter': obj,
            'device_class': obj.device_class,
            }
        return type('Group'+obj.name(), (_GroupConverter,), attrs)
    return obj


class BaseGroup(object):
    converters = [
        ]
