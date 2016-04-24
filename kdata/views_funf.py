from django.shortcuts import render
from django.core.exceptions import PermissionDenied
from django.core.urlresolvers import reverse
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect, Http404
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import ListView, DetailView, CreateView, UpdateView, FormView

import json
from . import models
from . import devices
from . import util

import logging
logger = logging.getLogger(__name__)



@csrf_exempt
def log(request, device_id=None, device_class=None):
    return JsonResponse(dict(status='success'))
@csrf_exempt
def post(request, device_id=None, device_class=None):
    logger.info('funf data: %r'%request.FILES)
    upload = request.FILES['uploadedfile']
    import os
    logger.info(os.getcwd())
    f = open('funf-data/%s'%upload.name, 'wb')
    #f.write(repr(request.body))
    f.write(upload.read())
    f.close()
    logger.info('file size: %s'%upload.size)
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
{"name": "funf",
"version":1,
"dataArchivePeriod":3600,
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
          "upload": { "url": \"https://dev.koota.zgib.net/funf/post/%(device_id)s",
                      "@schedule": {"interval": 600},
            "wifiOnly": true
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
    config = config_v2%dict(device_id=device_id)

    config = '\n'.join(x for x in config.split('\n') if not x.startswith('#'))
    json.loads(config)
    return HttpResponse(config, content_type='text/plain')

# How to access the data
# kdata.funf_decrypt.decrypt2(data, None, b'changeme')[:100]
