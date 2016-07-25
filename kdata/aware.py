from datetime import timedelta
from hashlib import sha256
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
from . import util
from . import views as kviews

import logging
logger = logging.getLogger(__name__)

AWARE_DOMAIN = 'https://aware.koota.zgib.net'
AWARE_DOMAIN_SIGNED = 'https://dev.koota.zgib.net'
PACKET_CHUNK_SIZE = 1000



class AwareDevice(devices.BaseDevice):
    """Basic Python class handling Aware devices"""
    _register_device = True
    desc = 'Aware device'
    AWARE_DOMAIN = AWARE_DOMAIN
    converters = devices.BaseDevice.converters + [
        converter.AwareUploads,
        converter.AwareTimestamps,
        converter.AwareTableData,
        converter.AwarePacketTimeRange,
        converter.AwareDataSize,
        converter.AwareRecentDataCounts,
        converter.AwareScreen,
        converter.AwareBattery,
        converter.AwareLight,
        converter.AwareWifi,
        converter.AwareSensorWifi,
        converter.AwareLocation,
        converter.AwareNetwork,
        converter.AwareApplicationNotifications,
        converter.AwareApplicationCrashes,
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
                                                    ))
        # TODO: http or https?
        url = self.AWARE_DOMAIN+url
        return url

class AwareDeviceValidCert(AwareDevice):
    """AWARE device, using a valid cert endpoint"""
    _register_device = True
    desc = 'Aware device (iOS)'
    AWARE_DOMAIN = AWARE_DOMAIN_SIGNED


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

# This is the JSON returned when a device is registered.
# Sensor settings:
# https://github.com/denzilferreira/aware-server/blob/master/aware_dashboard.sql#L298
base_config = dict(
    sensors=dict(
        status_mqtt=True,
        mqtt_server='aware.koota.zgib.net',
        mqtt_port=8883,
        mqtt_keep_alive=600,
        mqtt_qos=2,
        #mqtt_username='x',
        #mqtt_password='y',
        study_start=1464728400000,  # 1 june 2016 00:00
        #webservice_server='https://aware.koota.zgib.net/'+xxx,
        status_webservice=True,
        frequency_webservice=15,

        # meta-options
        frequency_clean_old_data=4,  # (0 = never, 1 = weekly, 2 = monthly)
        #study_id=1,            # If this is set to anything, not user modifiable
        status_crashes=True,
        status_esm=True,
        #webservice_wifi_only

        # Sensor config
        status_battery=True,
        status_screen=True,
        #status_bluetooth=False,
        #frequency_bluetooth=600,
        #status_light=True,
        status_accelerometer=False,
        frequency_accelerometer=10000000, #microseconds
        #frequency_light=10000000,  # microseconds
        #frequency_timezone=43200  # seconds
    ))
def aware_to_string(value):
    """AWARE requires setting values to be string.  Convert them"""
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)
def get_user_config(device):
    """Get a device's remote configuration.

    return value: Python dict object."""
    import copy
    config = copy.deepcopy(base_config)
    config['sensors']['mqtt_username'] = device.data.public_id
    config['sensors']['mqtt_password'] = device.data.secret_id
    #config['study_start'] = timezone.now().timestamp()*1000
    config['sensors']['webservice_server'] = device.qrcode_url()
    config['sensors']['status_webservice'] = True

    # This is the difference between a user being able to edit a
    # config themselves and not.
    #config['sensors']['study_id'] = 1

    # Aware requires it as a list of dicts.
    sensors = [dict(setting=k, value=aware_to_string(v))
               for k,v in config['sensors'].items()]

    config = [{'sensors': sensors}]
    return config



#
# AWARE API
#
@csrf_exempt
def register(request, secret_id, indexphp=None):
    """Initial URL that a device hits to register."""
    device = models.Device.get_by_secret_id(secret_id)
    device_cls = device.get_class()
    config = get_user_config(device_cls)

    # We have no other operation, basic study configuration.
    data = request.POST
    if 'device_id' in data:
        passwd = util.hash_mosquitto_password(device.secret_id)
        device.attrs['aware-device-uuid'] = data['device_id']
        device.attrs['aware-device-passwd_pbkdf2'] = passwd
        return JsonResponse(config, safe=False)
    # error return.
    return JsonResponse(dict(error="You should scan this with the Aware app.",
                             config=config),
                        status=400, reason="Scan with app")

@csrf_exempt
def create_table(request, secret_id, table, indexphp=None):
    """AWARE client creating table.  This is nullop for us."""
    # {'device_id': ['2e66087d-4afb-4a64-9316-67d737e21998'],
    #  'fields': ["_id integer primary key autoincrement,timestamp real default 0,device_id text default '',topic text default '',message text default '',status integer default 0,UNIQUE(timestamp,device_id)"]}
    #data = request.POST
    return HttpResponse(status=200, reason="We don't sync tables")

@csrf_exempt
def latest(request, secret_id, table, indexphp=None):
    """AWARE client getting most recent data point.

    Unlike the AWARE server, we don't return the latest row (that
    would send data out), but we get the stored timestamp of latest
    data and return that.
    """
    device = models.Device.get_by_secret_id(secret_id)
    device_cls = device.get_class()

    # Return the latest timestamp in our database.  Aware uses
    # this to know what data needs to be sent.
    ts = device.attrs.get('aware-last-ts-%s'%table, 0)
    if ts == 0:
        return JsonResponse([], safe=False)
    ts = int(float(ts))
    return JsonResponse([dict(timestamp=ts,
                              double_end_timestamp=ts,
                              double_esm_user_answer_timestamp=ts)],
                        safe=False)

@csrf_exempt
def insert(request, secret_id, table, indexphp=None):
    """AWARE client requesting data to be saved."""
    device = models.Device.get_by_secret_id(secret_id)
    # We do *not* check permissions here, since we are only POSTing
    # and no data can come out.  Unlike most devices, we must update
    # some internal state on POSTing, thus an unauthenticated getting
    # of a device class.
    device_cls = device.get_class()

    #device_uuid = request.POST['device_id']
    data = request.POST['data']  # data is bytes JSON data
    data_decoded = loads(data)
    data_sha256 = sha256(data.encode('utf8')).hexdigest()

    timestamp_column_name = 'timestamp'
    if 'double_end_timestamp' in data_decoded[0]:
        timestamp_column_name = 'double_end_timestamp'
    if 'double_esm_user_answer_timestamp' in data_decoded[0]:
        timestamp_column_name = 'double_esm_user_answer_timestamp'

    max_ts = max(float(row[timestamp_column_name]) for row in data_decoded)

    # Using this section, store all data in one packet.
    #data_with_probe = dumps(dict(table=table, data=data))
    #kviews.save_data(data_with_probe, device_id=device.device_id, request=request)

    # In this section, store data in chunks of size 500-1000.
    chunk_size = PACKET_CHUNK_SIZE
    data_separated = ( data_decoded[x:x+chunk_size]
                       for x in range(0, len(data_decoded), chunk_size) )
    for data_chunk in data_separated:
        data_chunk = dumps(data_chunk)
        data_with_probe = dumps(dict(table=table, data=data_chunk))
        kviews.save_data(data_with_probe, device_id=device.device_id, request=request)
        del data_chunk, data_with_probe
    del data, data_decoded, data_separated

    # Important conclusion: we must store the last timestamp.  Really
    # this and the section above should be an atomic operation!
    device.attrs['aware-last-ts-%s'%table] = max_ts
    return JsonResponse([dict(timestamp=max_ts,
                              double_end_timestamp=max_ts,
                              double_esm_user_answer_timestamp=max_ts,
                              dat_sha256=data_sha256),],
                        safe=False)

@csrf_exempt
def clear_table(request, secret_id, table, indexphp=None):
    """AWARE client requesting to clear a table.  Nullop for us."""
    return HttpResponse(reason="Not handled")




# /index.php/webservice/client_get_study_info/  # supposed to have API key
def study_info(request, secret_id, indexphp=None):
    """Returns "study info" that is presented when QR scanned.

    This function has no effect on config locking."""
    public_id = None
    if not secret_id:
        return JsonResponse({ })

    device = models.Device.get_by_secret_id(secret_id)
    public_id = device.public_id
    response = dict(study_name='Koota',
                    study_description=('Your device is linked to Koota. '
                                       'device_id=%s'%public_id),
                    researcher_first='Aalto Complex Systems',  # researcher name
                    researcher_last='',
                    researcher_contact='noreply@koota.cs.aalto.fi',
                    device_id='11'
                )
    return JsonResponse(response)



import qrcode
import io
from six.moves.urllib.parse import quote as url_quote
from django.conf import settings
def register_qrcode(request, public_id, indexphp=None):
    """Produce png AWARE qr code."""
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

    # Main registratioon link
    # AWARE has: 'index.php/webservice/index/$study_id/$api_key
    url(r'^v1/(?:1/)?(?P<secret_id>[0-9a-f]+)/?$', register,
        name='aware-register'),

    # Various table operations
    url(r'^v1/(?:1/)?(?P<secret_id>[0-9a-f]+)?/(?P<table>\w+)/create_table$', create_table,
        name='aware-create-table'),
    url(r'^v1/(?:1/)?(?P<secret_id>[0-9a-f]+)?/(?P<table>\w+)/latest$', latest,
        name='aware-latest'),
    url(r'^v1/(?:1/)?(?P<secret_id>[0-9a-f]+)?/(?P<table>\w+)/insert$', insert,
        name='aware-insert'),
    url(r'^v1/(?:1/)?(?P<table>\w+)/clear_table$', clear_table,
        name='aware-clear-table'),
]

# these urlpatters are hard-coded rooted at /index.php/.* so need to
# be handled specially.
urlpatterns_fixed = [
    # /index.php/webservice/client_get_study_info/  # supposed to have API key
    url(r'^webservice/client_get_study_info/(?P<secret_id>.*)',
        study_info,
        name='aware-study-info'),
]
