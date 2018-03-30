from datetime import datetime
import itertools
from json import dumps, loads
import random

from django import forms
from django.core.exceptions import PermissionDenied
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.urls import reverse, reverse_lazy
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect, Http404
from django.http import StreamingHttpResponse
from django.views.generic import ListView, DetailView, CreateView, UpdateView, FormView
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _
from django.template.response import TemplateResponse

from . import converter
from . import devices
from . import exceptions
from . import logs
from . import models
from . import permissions
from . import util
from . import views
from . import views_data


import logging
logger = logging.getLogger(__name__)
datalogger = logging.getLogger('kdata.datalog')


def user_groups(user):
    """User's group, sorted by reverse priority.

    Given a user object, return an interater over all
    kdata.models.Group objects, sorted by reverse priority.
    Equivalent to this code:
    models.Group.objects.filter(groupsubject__user=user).order_by('-priority')
    """
    groups = models.Group.objects.filter(groupsubject__user=user)
    groups.order_by('-priority')
    return groups
def user_merged_group_config(user):
    """Merged dict of config of all user's groups.

    Each group can have arbitrary JSON configuration (Group.config).
    This consists of dictionaries, which can be recursively merged to
    get some overall configuration.  If config conflicts, we can't
    solve that, but at least we can do something.

    """
    groups = user_groups(user)
    dicts = [ loads(g.config) for g in groups if g.config ]
    config = util.merge_dicts(*dicts)
    # Go through and update config with each grou, in reverse order.
    return config


def user_main_page(user):
    """Return the view name of this user's login page"""
    config = user_merged_group_config(user)
    return config.get('login_view_name', None)





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
    if not user.is_authenticated:
        # should never get here, we have login_required
        raise exceptions.NoDevicePermission()
    if request.method == 'POST':
        form = JoinGroupForm(request.POST)
        if form.is_valid():
            invite_code = form.cleaned_data['invite_code']
            groups = models.Group.objects.filter(invite_code=invite_code).exclude(invite_code="")
            context['groups'] = groups
            groups_str = ','.join(sorted(g.name for g in groups))

            if 'join' in request.POST and groups_str:
                # First stage.  User entered invite code.  We have to
                # present the data again, so that user can verify the
                # group that they are joining.
                c['round'] = 'verify'
                form.data = form.data.copy()
                form.data['groups'] = groups_str

            elif 'reject' in request.POST:
                return HttpResponseRedirect(reverse('main'))

            elif groups_str == form.cleaned_data['groups'] and 'accept' in request.POST:
                # Second stage.  User was presented the groups on the
                # last round, so now do the actual addition.
                c['round'] = 'done'
                for group in groups:
                    group_class = group.get_class()
                    #group.subjects.add(request.user)
                    if group.subjects.filter(id=user.id).exists():
                        continue
                    logs.log(request, 'user joining group',
                             obj='group='+group.slug, op='group_join')
                    models.GroupSubject.objects.create(user=user, group=group)
                    #print("added %s to %s"%(user, group))
                    group_class.setup_user(user)
                    # Record consent
                    privacy_stmt = group.get_privacy_stmt()
                    if privacy_stmt:
                        models.Consent.create(user, group, data=None, text=privacy_stmt)

            else:
                return HttpResponseRedirect(reverse('group-join'))
    else:
        # Initial, present box for invite code.
        c['round'] = 'initial'
        form = JoinGroupForm(initial=request.GET)
    c['form'] = form
    return TemplateResponse(request, 'koota/group_join.html',
                            context=context)




@login_required
def group_detail(request, group_name):
    context = c = { }
    group = models.Group.objects.get(slug=group_name)
    group_class = c['group'] = group.get_class()
    # If a researcher, allow researcher views.
    if (permissions.has_group_researcher_permission(request, group)
          or permissions.has_group_manager_permission(request, group)):
        # effective number of subjects: can be overridden
        c['is_staff'] = True
        c['n_subjects'] = sum(1 for _ in iter_subjects(group, group_class))
        c['is_researcher'] = group.is_researcher(request.user)
        c['is_manager'] = group.is_manager(request.user)
        c['is_admin'] = group.is_admin(request.user)
        if group.nonanonymous:
            c['group_subjects'] = group.groupsubject_set.order_by('user__username')
        else:
            c['group_subjects'] = group.groupsubject_set.all()
        #import IPython ; IPython.embed()
    # If a subject, allow subject views.
    if permissions.has_group_subject_permission(request, group):
        c['is_subject'] = group.is_subject(request.user)
        qs = models.GroupSubject.objects.filter(group=group, user=request.user)
        if qs.count() == 1:
            groupsubject = c['groupsubject'] = qs.get()
            converters_with_devices = [ ]
            for conv in group_class.converters:
                conv = get_group_converter(conv)
                # conv_devices = [ ]
                #device_classes = conv.device_class
                #if not isinstance(device_classes, (list, tuple)):
                #    device_classes = (device_class, )
                #for device_class in device_classes:
                #    devices.extend(groupsubject.allowed_devices(type=device_class))
                conv_devices = groupsubject.allowed_devices(conv)
                converters_with_devices.append((conv, conv_devices))
            c['subject_converters_with_devices'] = converters_with_devices
    # Log if there was no authority to view this.
    if 'is_subject' not in context and 'n_subjects' not in context:
        logs.log(request, 'view group denied',
                 obj='group='+group.slug, op='denied_group_detail')
        raise exceptions.NoGroupPermission()
    logs.log(request, 'view group',
                obj='group='+group.slug, op='group_detail')
    return TemplateResponse(request, 'koota/group_detail.html',
                            context=context)


def iter_subjects(group, group_class):
    """Iterate through all GroupSubject objects in group"""
    if hasattr(group_class, 'subjects_iter'):
        subjects = group_class.subjects_iter()
        subjects = (models.GroupSubject.objects.get(group=group, user=s)
                    for s in subjects)
    else:
        subjects = models.GroupSubject.objects.filter(group=group)
        if group.nonanonymous:
            subjects.order_by('user__username')
        else:
            subjects = list(subjects)
            random.shuffle(subjects)
    #subjects.sort(key=lambda subject: subject.user.id)
    for subject in subjects:
        yield subject
def iter_users_devices(group, group_class, group_converter_class):
    """Iterate (user, device_id) pairs in group"""
    if group_converter_class is None:
        for subject in iter_subjects(group, group_class):
            for device in subject.allowed_devices():
                yield subject, device
        return
    # device_class can be a list, in which case we check all of them.
    # If it is not a list, make it a list.
    device_classes = group_converter_class.device_class
    if not isinstance(device_classes, (list, tuple)):
        device_classes = [device_classes]
    #
    for subject in iter_subjects(group, group_class):
        for device_class in device_classes:
            for device in subject.allowed_devices(device_class=device_class):
                yield subject, device

def iter_group_data(group,
                    group_class,
                    group_converter_class,
                    converter_class,
                    converter_for_errors,
                    filter_queryset=None,
                    row_limit=None,
                    time_converter=lambda x: x,
                    handle_errors=True,
                    gs_id=None,
                    reverse_html_order=True,
                    hash_seed=None):
    """Core data iterator: (user, data, converter_data...)

    This abstracts out the core iteration of group data.  Basically,
    it takes as input some group information and a converter, runs
    that converter on all (user, device) pairs and iterates over all
    rows together.  There is a lot of support work to do this, and
    this does it all.  This is a separate function since the same
    logic may be needed several places.  There are many options to
    this because this should almost be embedded in other functions.
    The interface may evolve.

    Returns: iterator of rows.
        These rows are ['user_hash', 'device_hash'] + converter_rows.
    """
    #hash_subject = util.IntegerMap()
    #hash_device  = util.IntegerMap()
    if group.config:
        group_config = loads(group.config)
    else:
        group_config = { }

    for subject, device in iter_users_devices(group, group_class, group_converter_class):
        # We can request group data from only one subject.  In that
        # case, ignore anyone except that subject.  Subjects are
        # speciffied by the GroupSubject.id, abbreviated gs_id.
        if gs_id is not None:
            if subject.id != int(gs_id):
                continue

        # TODO: use subject_hash.  TODO: this duplicates code from
        # GroupSubject.hash(), unify (by getting the GroupSubject
        # object from above) if logic becomes complex.
        if group_config.get('data_has_raw_usernames', False):
            subject_hash = subject.user.username
            device_hash = device.public_id
        else:
            subject_hash = subject.hash(hash_seed=hash_seed)
            device_hash  = group.hash_do(device.public_id, hash_seed=hash_seed)

        # Fetch all relevant data
        queryset = models.Data.objects.filter(device_id=device.device_id, ).order_by('ts')
        # If row_limit, we are looking on HTML page and we reverse
        # things because this is more useful.
        if row_limit and reverse_html_order:
            queryset = queryset.reverse()
        # Filter the queryset however needed.  Two parts: group
        # limitations (left here), other user filtering (done via
        # filter_queryset callback.)
        if hasattr(converter_class, 'query'):
            queryset = converter_class.query(queryset)
        if group.ts_start: queryset = queryset.filter(ts__gte=group.ts_start)
        if group.ts_end:   queryset = queryset.filter(ts__lt=group.ts_end)
        if filter_queryset:
            queryset = filter_queryset(queryset)

        # Apply the converter.

        # If row_limit, we are looking at the HTML pages, and display
        # is reversed (see above).  In this case, we have to use
        # optimized_queryset_iterator_1.  It is slower, but it doesn't
        # matter since we have fewer rows.
        if row_limit and reverse_html_order:
            queryset = util.optimized_queryset_iterator_1(queryset)
        else:
            queryset = util.optimized_queryset_iterator(queryset)
        rows = ((x.ts, x.data) for x in queryset)
        converter = converter_class(rows=rows, time=time_converter, hash_seed=hash_seed)
        converter.errors = converter_for_errors.errors
        converter.errors_dict = converter_for_errors.errors_dict
        if handle_errors:
            rows = converter.run()
        else:
            rows = converter.convert(rows, time=time_converter)
        # Possibility to limit total data output (for testing purposes).
        if row_limit:
            fast_row_limit = getattr(converter, 'fast_row_limit', 500)
            #rows = util.time_slice_iterator(rows, 10)
            rows = itertools.islice(rows, min(row_limit, fast_row_limit))
        for row in rows:
            yield (subject_hash, device_hash) + row


@login_required
def group_data(request, group_name, converter, format=None, gs_id=None):
    context = c = { }
    group = models.Group.objects.get(slug=group_name)
    group_class = group.get_class()
    logs.log(request, 'view group data',
             obj='group='+group.slug, op='group_data')
    if not permissions.has_group_researcher_permission(request, group):
        logs.log(request, 'group data denied',
                 obj='group='+group.slug, op='denied_group_data')
        raise exceptions.NoGroupPermission()

    # Process the form and apply options
    form = c['select_form'] = views_data.DataListForm(request.GET)
    if form.is_valid():
        pass
    else:
        # Bad data, return early and make the user fix the form
        return TemplateResponse(request, 'koota/group_data.html', context)
    c['query_params_nopage'] = views_data.replace_page(request, '')

    c['group'] = group
    c['group_class'] = group_class
    group_converter_class = [ x for x in group_class.converters
                              if x.name() == converter ]
    if len(group_converter_class) == 0:
        return HttpResponse("No converter '%s' found."%converter,
                            content_type='text/plain',
                            status=404)
    group_converter_class = group_converter_class[0]
    group_converter_class = get_group_converter(group_converter_class)
    c['group_converter_class'] = group_converter_class

    converter_class = group_converter_class.converter
    converter_for_errors = converter_class(rows=None)

    def filter_queryset(queryset):
        """Callback to apply our queryset filtering operations."""
        #import IPython ; IPython.embed()
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


    table = iter_group_data(group, group_class,
                            group_converter_class, converter_class,
                            converter_for_errors=converter_for_errors,
                            filter_queryset=filter_queryset,
                            time_converter=time_converter,
                            row_limit=None if format else 100,
                            gs_id=gs_id, # limits to one subject if needed
                            )
    #if not format:
    #    table = itertools.islice(table, 1000)
    c['table'] = table


    context['download_formats'] = views_data.DOWNLOAD_FORMATS
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

def group_data_json(request, group_name, converter):
    group = models.Group.objects.get(slug=group_name)
    group_class = group.get_class()
    logs.log(request, 'view group data',
             obj='group='+group.slug, op='group_data')
    if not permissions.has_group_researcher_permission(request, group):
        logs.log(request, 'group data denied',
                 obj='group='+group.slug, op='denied_group_data')
        raise exceptions.NoGroupPermission()

    earliest = None
    latest = None

    # A lot of this is copied from group_data and should be merged.
    group_converter_class = [ x for x in group_class.converters
                              if x.name() == converter ]
    group_converter_class = group_converter_class[0]
    group_converter_class = get_group_converter(group_converter_class)

    converter_class = group_converter_class.converter

    for subject, device in iter_users_devices(group, group_class, group_converter_class):
        queryset = models.Data.objects.filter(device_id=device.device_id, ).order_by('ts')
        if hasattr(converter_class, 'query'):
            queryset = converter_class.query(queryset)
        if group.ts_start: queryset = queryset.filter(ts__gte=group.ts_start)
        if group.ts_end:   queryset = queryset.filter(ts__lt=group.ts_end)
        # This does start/end time and reversing, not needed here
        #if filter_queryset:
        #    queryset = filter_queryset(queryset)

        if queryset.exists():
            if earliest is None:
                earliest = queryset[0].ts
                latest = queryset.reverse()[0].ts
            else:
                earliest = min(earliest, queryset[0].ts)
                latest   = max(latest, queryset.reverse()[0].ts)
    data = { }
    data['data_exists'] = (earliest is not None)
    if data['data_exists']:
        data['data_earliest'] = earliest.timestamp()
        data['data_latest'] = latest.timestamp()
    else:
        data['data_earliest'] = data['data_latest'] = None
    return JsonResponse(data)


class GroupUpdate(UpdateView):
    """Allow admins to set basic group properties."""
    fields = ['name', 'desc', 'invite_code', 'config']
    template_name = 'koota/group_update.html'
    def get_object(self, queryset=None):
        slug = self.kwargs.get('group_name')
        g = models.Group.objects.get(slug=slug)
        if not permissions.has_group_admin_permission(self.request, g):
            raise exceptions.NoGroupPermission()
        return g



#
# Converters
#
class _GroupConverter(object):
    """A generic group converter.

    This wraps a regular converter, and includes information about
    what device clases a converter applies to.

    """
    @classmethod
    def name(cls):
        return cls.__name__
    desc = 'Base converter'
    converter = None
    device_class = None
def get_group_converter(obj):
    """Getter function to get group converter.

    If the object is already a group converter, just return it.  If it
    is not, then create a new GroupConverter which wraps the Converter
    and return that.
    """
    if issubclass(obj, converter._Converter):
        attrs = {
            'desc': obj.desc,
            'converter': obj,
            'device_class': obj.device_class,
            }
        return type('Group'+obj.name(), (_GroupConverter,), attrs)
    return obj



#
# Base group class
#
class BaseGroup(object):
    converters = [
        ]
    def __init__(self, dbrow):
        self.dbrow = dbrow
    def setup_user(self, user):
        """Initial user setup, such as creating devices.

        This method should be idempotent because it can be re-run to
        apply new settings.
        """
        pass

class TestersGroup(BaseGroup):
    converters = [
        ]
    group_devices = devices.all_device_classes



#
# Manager functions
#
class GroupSubjectForm(forms.ModelForm):
    class Meta:
        model = models.GroupSubject
        fields = ['notes']

@login_required
def group_subject_detail(request, group_name, gs_id):
    context = c = { }
    group = models.Group.objects.get(slug=group_name)
    if not (permissions.has_group_researcher_permission(request, group)
            or permissions.has_group_manager_permission(request, group)):
        logs.log(request, 'group subject detail denied',
                 obj='group=%s+sid=%s'%(group.slug,gs_id),
                 op='denied_group_subject_detail')
        raise exceptions.NoGroupPermission()
    groupcls = c['group'] = group.get_class()
    groupsubject = c['groupsubject'] = \
                   models.GroupSubject.objects.get(id=gs_id, group=group)
    c['is_researcher'] = group.is_researcher(request.user)
    c['is_manager'] = group.is_manager(request.user)

    # Notes form
    if request.method == 'POST':
        form = c['form'] = GroupSubjectForm(request.POST, instance=groupsubject)
        if form.is_valid():
            logs.log(request, 'group subject notes updating',
                obj='group=%s+sid=%s'%(group.slug,gs_id),
                op='group_subject_detail_notes',
                data_of=groupsubject.user)
            form.save()
    else:
        form = c['form'] = GroupSubjectForm(instance=groupsubject)

    logs.log(request, 'group subject detail',
             obj='group=%s+sid=%s'%(group.slug,gs_id),
             op='group_subject_detail',
             data_of=groupsubject.user)
    #import IPython ; IPython.embed()
    return TemplateResponse(request, 'koota/group_subject_detail.html',
                            context=context)



class GroupUserCreateForm(forms.Form):
    username = forms.CharField()
    def clean_username(self):
        User = django.contrib.auth.get_user_model()
        if User.objects.filter(username=self.cleaned_data['username']).exists():
            raise forms.ValidationError("Username already taken")
        return self.cleaned_data['username']

import django.contrib.auth
def group_user_create(request, group_name):
    context = c = { }
    group = models.Group.objects.get(slug=group_name)
    logs.log(request, 'group user create',
             obj='group=%s'%(group.slug),
             op='group_user_create')
    if not permissions.has_group_manager_permission(request, group):
        logs.log(request, 'group user create',
                 obj='group=%s'%(group.slug),
                 op='denied_group_user_create')
        raise exceptions.NoGroupPermission("Not a group manager.")
    if request.method == 'POST':
        form = GroupUserCreateForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            email = None
            password = None
            User = django.contrib.auth.get_user_model()
            user = User.objects.create_user(username,
                                            email,
                                            password)
            user.save()
            logs.log(request, 'group user create: success',
                     obj='group=%s+username=%s'%(group.slug, user.username),
                     op='group_user_create_success',
                     data_of=user)
            group_class = group.get_class()
            models.GroupSubject.objects.create(user=user, group=group)
            group_class.setup_user(user)
            c['success'] = True
    else:
        # Initial, present box for invite code.
        form = GroupUserCreateForm(initial=request.GET)
    c['form'] = form
    c['group'] = group
    return TemplateResponse(request, 'koota/group_user_create.html',
                            context=context)


def group_stats(request, group_name):
    context = c = { }
    group = models.Group.objects.get(slug=group_name)
    if not (permissions.has_group_researcher_permission(request, group)
            or permissions.has_group_manager_permission(request, group)):
        logs.log(request, 'group subject detail denied',
                 obj='group=%s+sid=%s'%(group.slug,gs_id),
                 op='denied_group_subject_detail')
        raise exceptions.NoGroupPermission()
    groupcls = c['group'] = group.get_class()

    devices = 0
    count = 0
    bytes = 0

    for subject, device in iter_users_devices(group, groupcls, group_converter_class=None):
        devices += 1
        #print(device.backend.count())
        count += device.backend.count()
        bytes_device = device.backend.bytes_total()
        if bytes_device:
            bytes += bytes_device
    data = ["devices: %s"%devices,
            "count: %s"%count,
                "bytes: %s"%util.human_bytes(bytes)]
    data = '\n'.join(data)
    return HttpResponse(data, content_type='text/plain')


def ensure_user_has_devices(user, devs, group):
    """Function to idempotently ensure user has devices.

    This would be used in the adding of users to groups.

    user: user object
    group: pyclass group object
    devs: list of devices and data to create.  Example:
          devs = [
              dict(cls=kdata.aware.AwareDevice, name="Phone"),
              dict(cls=kdata.devices.MurataBSN, name="Murata"),
              ]
    """
    for dev in devs:
        cls = dev['cls']
        name = dev['name']
        comment = dev.get('comment', 'automatically created')
        label_slug = dev.get('label', 'primary')

        created = False
        params = dict()
        qs = models.Device.objects.filter(
            user=user,
            type=cls.pyclass_name(),
            label__slug=label_slug)
        if qs.exists():
            continue
        #print("Creating %s for %s"%(cls, user))
        # create device
        model = models.Device
        if cls.dbmodel is not None:
            model = cls.dbmodel
        device = model(
            user=user,
            type=cls.pyclass_name(),
            name=name,
            comment=comment,
            label=models.DeviceLabel.objects.get(slug=label_slug))

        cls.create_hook(device, user=user)
        device.save()
        datalogger.info("auto-create-device u=%s cls=%s g=%s"%(user.username, cls.pyclass_name(), group.dbrow.slug))
