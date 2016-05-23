import json
from json import loads, dumps
import sqlite3
import tempfile
import textwrap
import time

from django.shortcuts import render
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.core.urlresolvers import reverse
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect, Http404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import ListView, DetailView, CreateView, UpdateView, FormView

from . import converter
from . import devices
from . import funf_decrypt
from . import models
from . import util

import logging
logger = logging.getLogger(__name__)

CONFIG_DOMAIN = settings.MAIN_DOMAIN
POST_DOMAIN = settings.POST_DOMAIN

@devices.register_device2(default=True)
class FunfJournal(devices._Device):
    desc = 'Funf-journal device'
    converters = devices._Device.converters + [ ]
    @classmethod
    def post(self, request):
        data = process_post(request)
        return dict(data=data,
                    response=JsonResponse(dict(status='success')))
    raw_instructions = textwrap.dedent("""'\
    <ol>
    <li>Install funf-journal from Google Play store</li>
    <li>Menu &rarr; Link to server</li>
    <li>Enter this URL: {config_url}</li>
    <li></li>
    <li></li>
    <li></li>
    <li></li>
    </ol>
    """)
    @classmethod
    def configure(cls, device):
        url = reverse('funf-journal-config', kwargs=dict(device_id=device.device_id))
        url = 'https://dev.koota.zgib.net'+url
        return dict(qr=False,
                    raw_instructions=cls.raw_instructions.format(config_url=url),
                    )

@csrf_exempt
def log(request, device_id=None, device_class=None):
    return JsonResponse(dict(status='success'))
@csrf_exempt
def process_post(request, device_id=None, device_class=None):
    #logger.info('funf data: %r'%request.FILES)
    upload = request.FILES['uploadedfile']
    import os
    #logger.info(os.getcwd())
    #f = open('funf-data/%s'%upload.name, 'wb')
    #f.write(repr(request.body))
    #f.write(upload.read())
    #f.close()
    #logger.info('file size: %s'%upload.size)
    upload_data = { }
    with tempfile.NamedTemporaryFile(dir='/tmp', prefix='tmp-funf-db-', delete=False) as tfile:
        #logger.info(tfile.name)
        data = upload.read()
        if b'SQLite' not in data[:20]:
            data = funf_decrypt.decrypt2(data, '', b'changeme')
        #logger.info(data[:80])
        tfile.write(data)
        tfile.flush()
        conn = sqlite3.connect(tfile.name)
        upload_data['data'] = conn.execute('select * from data').fetchall()
        upload_data['android_metadata'] = conn.execute('select * from android_metadata').fetchall()
        upload_data['file_info'] = conn.execute('select * from file_info').fetchall()
        upload_data['ts_received'] = time.time()
        upload_data['filename'] = upload.name
    conn.close()

    return dumps(upload_data)
    return JsonResponse(dict(status='success'))

config_v1 = """\
        {"@type":"edu.mit.media.funf.pipeline.BasicPipeline",
         "name":"remote_pipeline",
         "version":1,
          "archive": {
    "@schedule": {"interval": 3600},
            "compress": true,
            "password": "changeme"
          },
          "upload": { "url": \"https://dev.koota.zgib.net/funf/post/%(device_id)s",
                      "@schedule": {"interval": 600},
            "wifiOnly": true
 },
          "update": {
            "url": \"https://dev.koota.zgib.net/funf/config/%(device_id)s",
            "@schedule": {"interval": 600}
          },
         "data":[
#            {"@type": "edu.mit.media.funf.probe.builtin.BluetoothProbe", "@schedule": {"interval": 300, "maxScanTime": 60, "include_scan_started": true, "strict": false, "opportunistic": true}},
#            {"@type": "edu.mit.media.funf.probe.builtin.CellTowerProbe", "@schedule": {"interval": 600, "duration": 30, "strict": false, "opportunistic": true}},
#            {"@type": "edu.mit.media.funf.probe.builtin.HardwareInfoProbe", "@schedule": {"interval": 600, "duration": 30, "strict": false, "opportunistic": true}},
            {"@type": "edu.mit.media.funf.probe.builtin.ScreenProbe", "@schedule": {"interval": 0, "duration": 0, "strict": false, "opportunistic": true}},
            {"@type": "edu.mit.media.funf.probe.builtin.TimeOffsetProbe", "@schedule": {"interval": 21600, "duration": 0, "strict": false, "opportunistic": true}},
#            {"@type": "edu.mit.media.funf.probe.builtin.WifiProbe", "@schedule": {"interval": 600, "duration": 30, "include_scan_started": true, "strict": false, "opportunistic": true}},
            {"@type": "edu.mit.media.funf.probe.builtin.SmsProbe", "@schedule": {"interval": 43200, "duration": 0, "strict": false, "opportunistic": true}},
#            {"@type": "edu.mit.media.funf.probe.builtin.CallLogProbe", "@schedule": {"interval": 43200, "duration": 0, "strict": false, "opportunistic": true}},
#            {"@type": "edu.mit.media.funf.probe.builtin.AndroidInfoProbe", "@schedule": {"interval": 43200, "duration": 0, "strict": false, "opportunistic": true}},
#            {"@type": "edu.mit.media.funf.probe.builtin.LocationProbe", "@schedule": {"interval": 300, "duration": 30, "strict": false, "opportunistic": true}},
#            {"@type": "edu.mit.media.funf.probe.builtin.AccelerometerFeaturesProbe", "@schedule": {"interval": 300, "duration": 15, "strict": false, "opportunistic": true}},
#            {"@type": "edu.mit.media.funf.probe.builtin.AccountsProbe", "@schedule": {"interval": 43200, "duration": 0, "strict": false, "opportunistic": true}},
#            {"@type": "edu.mit.media.funf.probe.builtin.ActivityProbe", "@schedule": {"interval": 300, "duration": 15, "strict": false, "opportunistic": true}},
#            {"@type": "edu.mit.media.funf.probe.builtin.ApplicationsProbe", "@schedule": {"interval": 0, "duration": 0, "strict": false, "opportunistic": true}},
#            {"@type": "edu.mit.media.funf.probe.builtin.AudioFeaturesProbe", "@schedule": {"interval": 600, "duration": 15, "strict": false, "opportunistic": true}},
#            {"@type": "edu.mit.media.funf.probe.builtin.AudioMediaProbe", "@schedule": {"interval": 43200, "duration": 0, "strict": false, "opportunistic": true}},
            {"@type": "edu.mit.media.funf.probe.builtin.BatteryProbe", "@schedule": {"interval": 300, "duration": 0, "strict": false, "opportunistic": true}},
#            {"@type": "edu.mit.media.funf.probe.builtin.ContactProbe", "@schedule": {"interval": 43200, "duration": 0, "strict": false, "opportunistic": true}},
#            {"@type": "edu.mit.media.funf.probe.builtin.ImageMediaProbe", "@schedule": {"interval": 43200, "duration": 0, "strict": false, "opportunistic": true}},
#            {"@type": "edu.mit.media.funf.probe.builtin.LightSensorProbe", "@schedule": {"interval": 300, "duration": 5, "strict": false, "opportunistic": true}},
#            {"@type": "edu.mit.media.funf.probe.builtin.ProcessStatisticsProbe", "@schedule": {"interval": 600, "duration": 30, "strict": false, "opportunistic": true}},
#            {"@type": "edu.mit.media.funf.probe.builtin.ProximitySensorProbe", "@schedule": {"interval": 600, "duration": 10, "strict": false, "opportunistic": true}},
#            {"@type": "edu.mit.media.funf.probe.builtin.RunningApplicationsProbe", "@schedule": {"interval": 0, "duration": 0, "strict": false, "opportunistic": true}},
#            {"@type": "edu.mit.media.funf.probe.builtin.ServicesProbe", "@schedule": {"interval": 1200, "duration": 15, "strict": false, "opportunistic": true}},
#            {"@type": "edu.mit.media.funf.probe.builtin.TelephonyProbe", "@schedule": {"interval": 43200, "duration": 0, "strict": false, "opportunistic": true}},
#            {"@type": "edu.mit.media.funf.probe.builtin.TemperatureSensorProbe", "@schedule": {"interval": 1200, "duration": 10, "strict": false, "opportunistic": true}},
            {"@type": "edu.mit.media.funf.probe.builtin.VideoMediaProbe", "@schedule": {"interval": 43200, "duration": 0, "strict": false, "opportunistic": true}}
         ]
        }
"""

config_v2 = """\
{"name": "funf-%(device_id)s",
 "version":1,
# "dataArchivePeriod":3600,
 "dataRequests":{
    "edu.mit.media.funf.probe.builtin.LocationProbe": [
            { "PERIOD": 1800 }
        ],
    "edu.mit.media.funf.probe.builtin.HardwareInfoProbe": [
            { "PERIOD": 604800 }
        ],
    "edu.mit.media.funf.probe.builtin.BatteryProbe": [
            { "PERIOD": 300 }
        ]
 },
 "data": [
    "edu.mit.media.funf.probe.builtin.BatteryProbe",
    "edu.mit.media.funf.probe.builtin.ScreenProbe",
    "edu.mit.media.funf.probe.builtin.WifiProbe",
    "edu.mit.media.funf.probe.builtin.BluetoothProbe",
    {"@type": "edu.mit.media.funf.probe.builtin.SimpleLocationProbe",
     "@schedule": {"interval": 600},
     "goodEnoughAccuracy": 80,
     "maxWaitTime": 60}
   ],
 "upload": { "url": "%(post_domain)s%(post_path)s",
             "@schedule": {"interval": 600},
             "wifiOnly": true
    },
 "update": {"url": "%(config_domain)s%(config_path)s",
            "@schedule": {"interval": 3600}
           }
}
"""

@csrf_exempt
def config_funf(request, device_id=None):
    """Config dict data.

    This is a dummy URL that has no content, but at least will not 404.
    """
    if device_id is None:
        device_id = ''
    else:
        if not util.check_checkdigits(device_id):
            return JsonResponse(dict(ok=False, error='Invalid device_id checkdigits',
                                     device_id=device_id),
                                status=400, reason="Invalid device_id checkdigits")
    post_path = reverse('funf-journal-post', kwargs=dict(device_id=device_id))
    config_path = reverse('funf-journal-config', kwargs=dict(device_id=device_id))
    config = config_v2%dict(config_domain='https://'+CONFIG_DOMAIN,
                            post_domain='https://'+POST_DOMAIN,
                            post_path=post_path,
                            config_path=config_path,
                            device_id=device_id,
                            )

    config = '\n'.join(x for x in config.split('\n') if not x.startswith('#'))
    json.loads(config) # check for valid syntax
    return HttpResponse(config, content_type='text/plain')

# How to access the data
# kdata.funf_decrypt.decrypt2(data, None, b'changeme')[:100]




class _FunfConverter(converter._Converter):
    device_class = FunfJournal.pyclass_name()

class FunfProbes(_FunfConverter):
    desc = "Raw funf data"
    header = ["time", "time2", "probe", "data"]
    def convert(self, queryset, time=lambda x:x):
        for dt, data in queryset:
            #import IPython ; IPython.embed()
            data = loads(data)
            data2 = data['data']
            for row in data2:
                # Names from the database columns
                _id, name, timestamp, value = row
                value2 = loads(value)
                yield (time(timestamp),
                       time(value2['timestamp']),
                       name,
                       value,
                       )
FunfJournal.converters.append(FunfProbes)
