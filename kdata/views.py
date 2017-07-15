import functools
from hashlib import sha256
import json
import operator
import six

from django.shortcuts import render
from django.core.exceptions import PermissionDenied
from django.urls import reverse
from django.utils import timezone
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect, Http404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.views.generic import CreateView, DetailView, FormView, ListView
from django.views.generic import TemplateView, UpdateView

from . import devices
from . import exceptions
from . import group
from . import logs
from . import models
from . import permissions
from . import tokens
from . import util

import logging
logger = logging.getLogger(__name__)



# Create your views here.

@csrf_exempt
def post(request, device_id=None, device_class=None):
    #import IPython ; IPython.embed()
    if request.method != "POST":
        return JsonResponse(dict(ok=False, message="invalid HTTP method (must POST)"),
                            status=405)
    # Custom device code, if available.
    results = { }
    if device_class is not None:
        results = device_class.post(request)

    # Find device_id.  Try different things until found.
    if device_id is not None:
        pass
    elif 'device_id' in results:  # results from custom device code
        device_id = results['device_id']
    elif 'HTTP_DEVICE_ID' in request.META:
        device_id = request.META['HTTP_DEVICE_ID']
    elif 'device_id' in request.GET:
        device_id = request.GET['device_id']
    elif 'device_id' in request.POST:
        device_id = request.POST['device_id']
    else:
        return JsonResponse(dict(ok=False, error="No device_id provided"),
                            status=400, reason="No device_id provided")
    try:
        int(device_id, 16)
    except:
        logger.warning("Invalid device_id: %r"%device_id)
        return JsonResponse(dict(ok=False, error="Invalid device_id",
                                 device_id=device_id),
                            status=400, reason="Invalid device_id")
    device_id = device_id.lower()
    # Return an error if device checkdigits do not work out.  Since
    # the server may not have a complete list of all registered
    # devices, we need some way early-reject invalid device IDs.
    # Purpose is to protect against user misentering it, but not
    # attacks.
    if not util.check_checkdigits(device_id):
        logger.warning("Invalid device_id checkdigits: %r"%device_id)
        return JsonResponse(dict(ok=False, error='Invalid device_id checkdigits',
                                 device_id=device_id),
                            status=400, reason="Invalid device_id checkdigits")

    # Find the data to store
    if 'data' in results:  # results from custom device code
        data = results['data']
    elif 'data' in request.POST:
        data = request.POST['data']
    else:
        data = request.body
    # Encode everything to utf8.  the body is bytes, but request.POST
    # is decoded.  We need to encode in order to checksum and compute
    # len() properly.  TODO: make more efficient by not first decoding
    # the POST data.
    if not isinstance(data, six.binary_type):
        data = data.encode('utf8')

    # Get nonce if provided.  Nonce is just any string which is
    # returned directly to the client, and can be used for extra
    # security to ensure that communications are not replayed.
    nonce = None
    if 'HTTP_X_NONCE' in request.META:   nonce = request.META['HTTP_X_NONCE']
    elif 'nonce' in request.GET:         nonce = request.GET['nonce']
    elif 'nonce' in request.POST:        nonce = request.POST['nonce']

    # Check checksum if provided
    data_sha256 = sha256(data).hexdigest()
    if 'HTTP_X_SHA256' in request.META:
        if data_sha256 != request.META['HTTP_X_SHA256'].lower():
            return JsonResponse(dict(ok=False, error="Checksum mismatch"),
                                     status=400, reason="Checksum mismatch")

    # Store data in DB.  (Uses django models for now, but should
    # be made more efficient later).
    rowid = save_data(data=data, device_id=device_id, request=request)
    logger.debug("Saved data from device_id=%r"%device_id)

    # HTTP response
    if 'response' in results:
        return results['response']
    response = dict(ok=True,
                    data_sha256=data_sha256,
                    bytes=len(data),
                    #rowid=rowid,
                    )
    if nonce is not None:
        response['nonce'] = nonce
    if 'HTTP_X_ROWID' in request.META:
        response['rowid'] = rowid
    return JsonResponse(response)

def save_data(data, device_id, request=None,
              received_ts=None, data_ts=None):
    """Save data which our server receives.

    This is the master "save data in DB" function.

    Arguments:
    data:        data (normally binary, though this is TODO)
    device_id:   device ID under which to save.  The checksum is
                 checked.
    request:     the HttpRequest object.  Used to get remote IP
                 address.
    received_ts: If given, override the automatic "data packet
                 received" timestamp
    data_ts:     If given, this is used as the timestamp to index by,
                 and represents the time the data was actually received.
    """
    if not isinstance(data, (str, bytes)):
        raise ValueError("save_data data must be str or bytes!")
    device_id = device_id.lower()
    if not util.check_checkdigits(device_id):
        raise exceptions.InvalidDeviceID("Invalid device ID: checkdigits invalid.")
    remote_ip = '127.0.0.1'
    if request is not None:
        remote_ip = request.META['REMOTE_ADDR']
    # Actual saving process.
    row = models.Data(device_id=device_id, ip=remote_ip, data=data)
    row.data_length = len(data)
    row.save()
    # If necessary, set custom timestamps on the data.  It's unlikely
    # that we get both, so save twice.
    if received_ts is not None:
        if isinstance(received_ts, int):
            received_ts = timezone.make_aware(timezone.datetime.fromtimestamp(received_ts))
        row.ts_received = received_ts
        row.save()
    if data_ts is not None:
        if isinstance(data_ts, int):
            data_ts = timezone.make_aware(timezone.datetime.fromtimestamp(data_ts))
        row.ts = data_ts
        row.save()
    # Return row_id of inserted data.
    row_id = row.id
    del row, data
    return row_id



@csrf_exempt
def log(request, device_id=None, device_class=None):
    """PR-support function: test function to accept and discard log data."""
    return JsonResponse(dict(status='success'))



@csrf_exempt
def config(request, device_class=None):
    """Config dict data.

    This is a dummy URL that has no content, but at least will not 404.
    """
    from django.conf import settings
    from codecs import encode
    data = { }
    if 'device_id' in request.GET:
        pass
        # Any config by device
    cert_der = encode(open(settings.KOOTA_SSL_CERT_DER,'rb').read(), 'base64')
    cert_pem = encode(open(settings.KOOTA_SSL_CERT_PEM,'rb').read(), 'base64')
    data['selfsigned_cert_der'] = cert_der.decode('ascii')
    data['selfsigned_cert_pem'] = cert_pem.decode('ascii')
    return JsonResponse(data)


#
# General
#
class MainView(TemplateView):
    template_name = 'koota/main.html'
    def get_context_data(self):
        context = super(MainView, self).get_context_data()
        if not self.request.user.is_anonymous:
            context['anon_id_token'] = tokens.get_user_anon_id_token(self.request.user)
        return context

#
# Device management
#
class DeviceListView(ListView):
    template_name = 'koota/device_list.html'
    model = models.Device
    allow_empty = True

    def dispatch(self, request, *args, **kwargs):
        """Handle anonymous users by redirecting to main"""
        if request.user.is_anonymous:
            return HttpResponseRedirect(reverse('main'))
        return super(DeviceListView, self).dispatch(request, *args, **kwargs)
    def get_context_data(self, **kwargs):
        context = super(DeviceListView, self).get_context_data(**kwargs)
        context['device_create_url'] = reverse('device-create')
        return context
    def get_queryset(self):
        # fixme: return "not possible" if not logged in
        if self.request.user.is_superuser:
            queryset = self.model.objects.all().order_by('_public_id')
        else:
            queryset = self.model.objects.filter(user=self.request.user)\
                                .order_by('archived', 'label__order', 'type', '_public_id')
        return queryset

class DeviceConfig(UpdateView):
    template_name = 'koota/device_config.html'
    model = models.Device
    fields = ['name', 'type', 'label', 'archived', 'comment']

    def get_object(self):
        """Get device model object, testing permissions"""
        obj = self.model.get_by_id(self.kwargs['public_id'])
        if not permissions.has_device_config_permission(self.request, obj):
            raise exceptions.NoDevicePermission("No permission for device")
        return obj
    def get_context_data(self, **kwargs):
        """Override template context data with special instructions from the DeviceType object."""
        context = super(DeviceConfig, self).get_context_data(**kwargs)
        device_class = context['device_class'] = self.object.get_class()
        context['device'] = self.object
        context.update(device_class.config_context())
        context.update(device_class.get_raw_instructions(context=context,
                                                         request=self.request))
        device_data = models.Data.objects.filter(device_id=self.object.device_id)
        context['data_number'] = device_data.count()
        if context['data_number'] > 0:
            context['data_earliest'] = device_data.order_by('ts').first().ts
            context['data_latest'] = device_data.order_by('-ts').first().ts
            context['data_latest_data'] = device_data.order_by('-ts').first().data
        # Handle the instructions template
        #
        return context
    def form_valid(self, *args, **kwargs):
        logs.log(self.request, 'edit device', user=self.request.user,
                 obj=self.object.public_id, op='update',
                 data_of=self.object.user)
        return super(DeviceConfig, self).form_valid(*args, **kwargs)
    def get_success_url(self):
        if 'gs_id' in self.kwargs:
            return ''
        return reverse('device-config', kwargs=dict(public_id=self.object.public_id))
    def get_form(self, *args, **kwargs):
        """Get a form that has device type choices set per-user

        See DeviceCreate.get_Form().
        """
        # This is a little bit hackish.  We rely on the code from
        # DeviceCreate.get_form and DeviceCreate.get_user so that we
        # don't have to do it ourselves.  This code could sometime be
        # abstracted out of the.
        base_form = super(DeviceConfig, self).get_form(*args, **kwargs)
        form = DeviceCreate.get_form(self,
                                     base_form=base_form,
                                     user=DeviceCreate.get_user(self))
        return form

    def get(self, request, *args, **kwargs):
        return self.handle(request, *args, **kwargs)
    def post(self, request, *args, **kwargs):
        return self.handle(request, *args, **kwargs)
    def handle(self, request, *args, **kwargs):
        method = request.method
        # self.object: django model
        # device: Python class
        self.object = self.get_object()   # Permissions handled HERE.
        device = self.object.get_class()
        #device_config_form = self.get_form()  # done in get_context_data
        all_valid = True        # are any forms invalid?
        any_changed = False     # did any forms change?
        context = self.get_context_data()
        del context['form']     # this is added below, not automatically

        # Allow this configuration only if unlocked OR researcher.
        is_staff = False
        is_locked = False
        if self.object.label.analyze:
            for grp in group.user_groups(self.object.user):
                if grp.locked:
                    is_locked = True
            if is_locked:
                if permissions.has_device_manager_permission(self.request, self.object):
                    is_staff = True
        context['is_locked'] = is_locked and not is_staff

        if not is_locked or is_staff:
            # Custom forms to set device attributes.
            if hasattr(device, 'config_forms'):
                # Handle all of our custom forms.
                log_func = functools.partial(logs.log, request=request,
                                             data_of=self.object.user,
                                             obj=self.object.public_id)
                ret = util.run_config_form(forms=device.config_forms,
                                                    attrs=self.object.attrs,
                                                    method=method,
                                                    POST=request.POST,
                                               log_func=log_func)
                custom_forms, all_valid, any_changed = ret
                if method == 'POST':
                    # Update objects
                    self.object = self.get_object()
                    device = self.object.get_class()
                    context.update(self.get_context_data())

                context['custom_forms'] = custom_forms

            # Main model form (reproducing logic from UpdateView).
            # This is second because the custom forms regenerate the
            # context, which includes the "wrong" logic for updating
            # the form.  We have multiple independent forms on the
            # same page, and we have to handle the validation logic
            # for only the one which is submitted!  This is really
            # beyond what we should be using class-based views for,
            # but we can change it all someday.
            form_class = self.get_form_class()
            if method == 'POST' and 'submit_device_config' in request.POST:
                form = form_class(data=request.POST, instance=self.object, prefix='config_')
                if form.has_changed():    any_changed = True
                if not form.is_valid():   all_valid = False
                if form.is_valid():
                    self.object = form.save()
                    device = self.object.get_class()
                    context.update(self.get_context_data())
                    logs.log(self.request, 'edit device', user=self.request.user,
                             obj=self.object.public_id, op='update',
                             data_of=self.object.user)
                else:
                    pass
            else:
                form = form_class(instance=self.object, prefix='config_')
            context['form'] = form

        context['all_valid'] = all_valid
        context['any_changed'] = any_changed
        return self.render_to_response(context)









import qrcode
import io
from six.moves.urllib.parse import quote as url_quote
from django.conf import settings
def device_qrcode(request, public_id):
    device = models.Device.get_by_id(public_id)
    if not permissions.has_device_config_permission(request, device):
        raise exceptions.NoDevicePermission("No permission for device")
    #device_class = devices.get_class(self.object.type).qr_data(device=device)
    main_host = "https://{0}".format(settings.MAIN_DOMAIN)
    post_host = "https://{0}".format(settings.POST_DOMAIN)
    data = [('post', post_host+reverse('post')+'?device_id=%s'%device.secret_id),
            ('config', main_host+'/config?device_id=%s&device_type=%s'%(
                device.secret_id, device.type)),
            ('device_id', device.secret_id),
            ('public_id', device.public_id),
            ('secret_id', device.secret_id),
            ('device_type', device.type),
            ('selfsigned_post', 'https://'+settings.POST_DOMAIN_SS+reverse('post')),
            ('selfsigned_cert_der_sha256', settings.KOOTA_SSL_CERT_DER_SHA256),
            ('selfsigned_cert_pem_sha256', settings.KOOTA_SSL_CERT_PEM_SHA256),
             ]
    uri = 'koota:?'+'&'.join('%s=%s'%(k, url_quote(v)) for k,v in data)
    img = qrcode.make(uri, border=4, box_size=2,
                     error_correction=qrcode.constants.ERROR_CORRECT_L)
    cimage = io.BytesIO()
    img.save(cimage)
    cimage.seek(0)
    return HttpResponse(cimage.getvalue(), content_type='image/png')



class DeviceCreate(CreateView):
    template_name = 'koota/device_create.html'
    _model = models.Device
    fields = ['name', 'type', 'label', 'comment']

    @property
    def model(self):
        """Handle Device classes which have a different DB model.
        """
        model = self._model
        if self.request.method == 'POST':
            device_class = self.request.POST.get('type', None)
            if device_class is not None:
                dbmodel = devices.get_class(device_class).dbmodel
                if dbmodel is not None:
                    model = dbmodel
        return model
    #def get_form_class(*args, **kwargs):
    #    """Get form class, taking into account different types of db Devices.
    #
    #    The whole point of this is that not every device should be a
    #    models.Device.  For example, surveys are instances of
    #    models.SurveyDevice.  Instead of needing to create this
    #    ourselves in the devices.BaseDevice.create_hook, and link them,
    #    we can create from the start.
    #    """
    #    from django.forms import modelform_factory
    #    # Default model
    #    model = self.model
    #    # Override model, if we have been POSTed to, and we know the
    #    # expected device_type, and that class overrides our database
    #    # model.
    #    if self.request.method == 'POST':
    #        device_class = self.request.POST.get('type', None)
    #        if device_class is not None:
    #            dbmodel = devices.get_class(device_class).dbmodel
    #            if dbmodel is not None:
    #                model = dbmodel
    #    # The following two lines are taken from
    #    # ModelFormMixin.get_form_class and FormMixin.get_form.
    #    form_class = modelform_factory(model, fields=self.fields)
    #    form = form_class(**self.get_form_kwargs())
    def get_form(self, *args, **kwargs):
        """Get the form and override the available device types based on user.
        """
        # The following hackish thing is so that this method can be
        # used for both this (DeviceCreate) and the DeviceConfig
        # classes.  Both need to adjust the device form so that the
        # available devices depend on what the user has access to.
        if 'base_form' in kwargs:
            form = kwargs['base_form']
            user = kwargs['user']
        else:
            form = super(DeviceCreate, self).get_form(*args, **kwargs)
            user = self.get_user()
        #

        # This gets only the standard choices, that all users should
        # have.
        choices = [(None, '----(select one)----') ]
        std_choices = devices.get_choices()
        std_choices = sorted(std_choices, key=lambda row: row[1].lower())
        choices.extend(std_choices)
        # Extend to extra devices that this user should have.  TODO:
        # make this user-dependent.
        #choices.extend([('kdata.survey.TestSurvey1', 'Test Survey #1'),])
        for group in user.subject_of_groups.all():
            cls = group.get_class()
            if hasattr(cls, 'group_devices'):
                group_choices = [ ]
                #import IPython ; IPython.embed()
                for dev in cls.group_devices:
                    row = dev._devicechoices_row()
                    # This is O(N^2) but deal with it later since
                    # number of devices for any one person should not
                    # grow too large.
                    #if row not in choices:
                    #    choices.append(row)
                    group_choices.append(row)
                group_choices = sorted(group_choices, key=lambda row: row[1].lower())
                choices.append((group.desc, group_choices))
        #choices = sorted(choices, key=lambda row: row[1].lower())
        form.fields['type'].choices = choices
        form.fields['type'].widget.choices = choices
        return form
    def form_valid(self, form):
        """Create the device."""
        user = self.request.user
        device_user = self.get_user()  # this could be for a study subject...
        if not user.is_authenticated:
            raise exceptions.LoginRequired()
        # Who are we creating this device for?  We have to handle that cleverly.
        if user == device_user:
            # Creating for self, no extra permissions needed
            pass
        elif user != device_user:
            # Actual user (request.user) must have permissions for
            # managing the group.
            if not permissions.has_device_manager_permission(self.request,
                                                             device=None,
                                                             subject=device_user):
                raise exceptions.NoGroupPermission(
                    "You can't create devices for subjects of this group")

        form.instance.user = device_user
        device_class = devices.get_class(form.cleaned_data['type'])
        device_class.create_hook(form.instance, user=device_user)
        logs.log(self.request, 'create device', user=self.request.user,
                 obj=form.instance.public_id, op='create',
                 data_of=form.instance.user)
        return super(DeviceCreate, self).form_valid(form)
    def get_success_url(self):
        """Redirect to device config page."""
        self.object.save()
        self.object.refresh_from_db()
        #print 'id'*5, self.object.device_id
        if 'gs_id' in self.kwargs:
            return reverse('group-subject-device-config',
                           kwargs=dict(group_name=self.kwargs['group_name'],
                                       gs_id=self.kwargs['gs_id'],
                                       public_id=self.object.public_id))
        return reverse('device-config', kwargs=dict(public_id=self.object.public_id))
    def get_user(self):
        """Get the user for hich we are creating a device for.

        If we have 'gs_id' in our kwargs, we are making a device for a
        user who isn't us.

        """
        if 'gs_id' in self.kwargs:
            groupsubject = models.GroupSubject.objects.get(id=self.kwargs['gs_id'])
            user = groupsubject.user
        else:
            user = self.request.user
        return user
    def get_context_data(self, **kwargs):
        """Update actual user (current user or group subject) into context"""
        context = super(DeviceCreate, self).get_context_data(**kwargs)
        context['actual_user'] = self.get_user()
        return context


@require_http_methods(['POST'])
def mark_device(request, public_id, operation=None):
    if operation is None:
        operation = request.POST['operation']
    device = models.Device.get_by_id(public_id)
    if not permissions.has_device_config_permission(request, device):
        raise exceptions.NoDevicePermission("No permission for device")

    if operation == 'dont-have':
        device.attrs['dont_have'] = True
    if operation == 'not-linking':
        device.attrs['not_linking'] = True
    logs.log(request, "marking %s"%operation, obj=public_id,
                 op='mark-device-'+operation, data_of=device.user)

    return HttpResponseRedirect(request.POST['next'])
