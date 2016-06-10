from datetime import timedelta
from json import loads, dumps
import textwrap
import time
from six.moves.urllib import parse as urlparse

from django.conf.urls import url, include
from django.core.urlresolvers import reverse
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect, Http404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from . import devices
from . import converter
from . import exceptions
from . import models
from . import permissions
from . import views as kviews

import logging
logger = logging.getLogger(__name__)



class AwareDevice(devices.BaseDevice):
    _register_device = True
    desc = 'Aware device'
    converters = devices.BaseDevice.converters + [
        converter.AwareUploads,
        converter.AwareTableData,
        converter.AwareScreen,
        converter.AwareBattery,
        converter.AwareLight,
        converter.AwareWifi,
        converter.AwareSensorWifi,
        converter.AwareLocation,
        converter.AwareNetwork,
        converter.AwareCalls,
        converter.AwareMessages,
    ]
    @classmethod
    def post(self, request):
        data = process_post(request)
        return dict(data=data,
                    response=JsonResponse(dict(status='success')))
    raw_instructions = textwrap.dedent("""'\
    <ol>
    <li>See the <a href="https://github.com/CxAalto/koota-server/wiki/Aware">instructions on the github wiki</a>.
    <li>URL is {study_url}</li>
    <li></li>
    <li></li>
    <li></li>
    </ol>

    <img src="{qrcode_img_path}"></img>
    """)
    @classmethod
    def configure(cls, device):
        device_class = device.get_class()
        url = device_class.qrcode_url()
        qrcode_img_path = reverse('aware-register-qr',
                                  kwargs=dict(public_id=device.public_id))
        raw_instructions = raw_instructions=cls.raw_instructions.format(
            study_url=url,
            qrcode_img_path=qrcode_img_path,)
        return dict(qr=False,
                    raw_instructions=raw_instructions,
                    )
    def qrcode_url(self):
        """Return the data contained in the QRcode.

        This is the data used for registration."""
        secret_id = self.data.secret_id
        url = reverse('aware-register', kwargs=dict(indexphp='index.php',
                                                    secret_id=secret_id,
                                                    rest=''))
        # TODO: http or https?
        url = 'https://aware.koota.zgib.net'+url
        return url

#config = 
#$decode->{'sensors'}[] = array('setting' => 'status_mqtt','value' => 'true' );
#$decode->{'sensors'}[] = array('setting' => 'mqtt_server', 'value' => $mqtt_config['mqtt_server']);
#$decode->{'sensors'}[] = array('setting' => 'mqtt_port', 'value' => $mqtt_config['mqtt_port']);
#$decode->{'sensors'}[] = array('setting' => 'mqtt_keep_alive','value' => '600');
#$decode->{'sensors'}[] = array('setting' => 'mqtt_qos','value' => '2');
#$decode->{'sensors'}[] = array('setting' => 'status_esm','value' => 'true' );
#$decode->{'sensors'}[] = array('setting' => 'mqtt_username', 'value' => $device_id);
#$decode->{'sensors'}[] = array('setting' => 'mqtt_password', 'value' => $pwd);
#$decode->{'sensors'}[] = array('setting' => 'study_id', 'value' => $study_id);
#$decode->{'sensors'}[] = array('setting' => 'study_start', 'value' => (string) round(microtime(true) * 1000));
#$decode->{'sensors'}[] = array('setting' => 'webservice_server', 'value' => base_url().'index.php/webservice/index/'.$study_id.'/'.$api_key);
#$decode->{'sensors'}[] = array('setting' => 'status_webservice', 'value' => 'true');

base_config = dict(
    sensors=dict(
        status_mqtt='true',
        mqtt_server='aware.koota.zgib.net',
        mqtt_port=8883,
        mqtt_keep_alive=600,
        mqtt_qos=2,
        status_esm='true',
        #mqtt_username='x',
        #mqtt_password='y',
        #study_id='none',
        #study_start=0,
        #webservice_server='https://aware.koota.zgib.net/'+xxx,


        # per-sensor config
        status_battery=True,

        status_bluetooth=False,
        #frequency_bluetooth=600,
    ))
def get_user_config(device):
    import copy
    config = copy.deepcopy(base_config)
    config['sensors']['mqtt_username'] = device.data.public_id
    config['sensors']['mqtt_password'] = device.data.secret_id
    #config['sensors']['study_id'] = 'none'
    #config['study_start'] = timezone.now().timestamp()*1000
    #config['webservice_server'] = device.qrcode_url()
    # Aware requires it as a list of dicts.
    config['sensors'] = [dict(setting=k, value=v)
                         for k,v in config['sensors'].items()]

    #config = {0: {'sensors':config['sensors']},
    #          #1: {'plugins':config['plugins']},
    #          }
    config = [{'sensors': config['sensors']}]
    return config






@csrf_exempt
def register(request, secret_id=None, rest=None, indexphp=None):
    if rest is None:
        rest = ''
    # Parse the extra operation stuff we have.
    rest = rest.split('/')
    table = rest[0]  # this is the type of data
    operation = None
    if len(rest) > 1:
        operation = rest[1]

    device = models.Device.get_by_secret_id(secret_id)
    device_cls = device.get_class()

    if table == '':
        # We have no other operation, basic study configuration.
        data = request.POST
        #if 'device_id' not in data:
        #    return JsonResponse(dict(error="You should scan this with the Aware app."))
        import os
        from django.contrib.auth.hashers import PBKDF2PasswordHasher
        import base64
        salt = base64.b64encode(os.urandom(15)).decode('ascii')
        passwd = PBKDF2PasswordHasher().encode(device.secret_id, salt, iterations=50000)
        # Following two lines to put it in MQTT format
        passwd = passwd.replace('_', '$', 1)
        passwd = passwd.replace('pbkdf2', 'PBKDF2')
        device.attrs['aware-device-uuid'] = data['device_id']
        device.attrs['aware-device-passwd_pbkdf2'] = passwd
        config = get_user_config(device_cls)
        return JsonResponse(config, safe=False)
        return JsonResponse({})

    elif operation == 'create_table':
        # {'device_id': ['2e66087d-4afb-4a64-9316-67d737e21998'],
        #  'fields': ["_id integer primary key autoincrement,timestamp real default 0,device_id text default '',topic text default '',message text default '',status integer default 0,UNIQUE(timestamp,device_id)"]}
        data = request.POST
        #logger.error("fields for %s: %s"%(table, data['fields']))
        return HttpResponse(status=200, reason="We don't sync tables")
        #logger.debug(request.path_info)

    elif operation == 'latest':
        # Return the latest timestamp in our database.  Aware uses
        # this to know what data needs to be sent.
        ts = device.attrs.get('aware-last-ts-%s'%table, 0)
        #logger.error("latest: %s %s", table, time.strftime('%F %T', time.localtime(float(ts)/1000.)))
        return JsonResponse([dict(timestamp=ts,
                                  double_end_timestamp=ts,
                                  double_esm_user_answer_timestamp=ts)],
                            safe=False)

    elif operation == 'insert':
        #logger.error(request.body[:80])
        device_uuid = request.POST['device_id']  # not used
        data = request.POST['data']  # data is bytes JSON data
        #logger.error("The data: %r"%data[:80])
        data_decoded = loads(data)

        timestamp_column_name = 'timestamp'
        if 'double_end_timestamp' in data_decoded[0]:
            timestamp_column_name = 'double_end_timestamp'
        if 'double_esm_user_answer_timestamp' in data_decoded[0]:
            timestamp_column_name = 'double_esm_user_answer_timestamp'

        max_ts = max(float(row[timestamp_column_name]) for row in data_decoded)
        data_with_probe = dumps(dict(table=table, data=data))
        #logger.error("insert: %s %s", table, time.strftime('%F %T', time.localtime(float(max_ts)/1000.)))

        kviews.save_data(data_with_probe, device_id=device.device_id, request=request)
        device.attrs['aware-last-ts-%s'%table] = max_ts
        return HttpResponse()

    elif operation == 'clear_table':
        pass
        return HttpResponse(reason="Not handled")

    else:
        logger.error("Unknown aware request: %s", rest)


    return HttpResponse(status=400, reason="We don't know how to handle this request")

def create_table(request, secret_id, table, indexphp=None):
    return HttpRespnse(reason="Not handled")


# /index.php/webservice/client_get_study_info/  # supposed to have API key
def study_info(request):
    response = dict(study_name='study name',
                    study_description='study_desc',
                    researcher_first='firstname',  # researcher email
                    researcher_last='listname',
                    researcher_contact='noone@koota.cs.aalto.fi',
                )
    return JsonResponse(response)


def aware_config(request, public_id=None):
    """Config dict data.

    This is a dummy URL that has no content, but at least will not 404.
    """


import qrcode
import io
from six.moves.urllib.parse import quote as url_quote
from django.conf import settings
def register_qrcode(request, public_id, indexphp=None):
    """HTTP endpoint for aware QR codes."""
    device = models.Device.get_by_id(public_id)
    if not permissions.has_device_config_permission(request, device):
        raise exceptions.NoDevicePermission()
    device_class = device.get_class()
    url = device_class.qrcode_url()
    data = url
    img = qrcode.make(data, border=4, box_size=6,
                     error_correction=qrcode.constants.ERROR_CORRECT_L)
    cimage = io.BytesIO()
    img.save(cimage)
    cimage.seek(0)
    return HttpResponse(cimage.getvalue(), content_type='image/png')



urlpatterns = [
    url(r'^v1/(?P<public_id>[0-9a-f]+)/qr.png$', register_qrcode,
        name='aware-register-qr'),
    url(r'^v1/(?P<secret_id>[0-9a-f]+)?(?:/(?P<rest>.*))?$', register,
        name='aware-register'),

    url(r'^v1/(?P<secret_id>[0-9a-f]+)?/(?P<table>\w+)/create_table$', create_table,
        name='aware-create-table'),
    url(r'^v1/(?P<secret_id>[0-9a-f]+)?/(?P<table>\w+)/latest$', latest,
        name='aware-latest'),
    url(r'^v1/(?P<secret_id>[0-9a-f]+)?/(?P<table>\w+)/insert$', insert,
        name='aware-insert'),
    url(r'^v1/(?P<secret_id>[0-9a-f]+)?/(?P<table>\w+)/clear_table$', clear_table,
        name='aware-clear-table'),
]
