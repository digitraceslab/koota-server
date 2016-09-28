"""Murata Bed Sensor Node

http://www.murata.com/en-eu/products/sensor/accel/sca10h_11h/sca11h
"""
import json
import logging
import textwrap

from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .. import converter
from ..devices import BaseDevice, register_device
from .. import models
from ..views import save_data

LOGGER = logging.getLogger('kdata.devices.muratabsn')


from defusedxml.ElementTree import fromstring as xml_fromstring
@register_device(default=True, alias='MurataBSN')
class MurataBSN(BaseDevice):
    converters = BaseDevice.converters + [
                  converter.MurataBSN,
                  converter.MurataBSNDebug,
                  converter.MurataBSNSafe,
                 ]
    raw_instructions = textwrap.dedent("""\
    See <a href="https://github.com/CxAalto/koota-server/wiki/MurataBSN">the wiki page</a>.
    The <tt>device_secret_id</tt> to use for the "Node ID" on the "Communication Settings" page
    is <tt>{device.secret_id}</tt>.  Do <b>not</b> put in your Koota username and password,
    leave them as <tt>x</tt> or something.
    """)
    @classmethod
    def post(cls, request):
        doc = xml_fromstring(request.body)
        node = doc[0][0]
        device_id = node.attrib['id']

        return dict(device_id=device_id,
                    )
    @classmethod
    def configure(cls, device):
        return dict(raw_instructions=cls.raw_instructions.format(device=device),
                    )


# pylint disable=wrong-import-order,wrong-import-position

@csrf_exempt
@require_http_methods(['POST'])
def murata_calibrate(request, mac_addr=None):
    # pyli nt disable=redefined-variable-type,unused-variable
    # BSN syncs its FW version details and BCG calibration parameters
    # with cloud server after power on/reset and then every 24 hours.
    # dev_id is the network "nodename"
    LOGGER.info("Calibrate received: %s %s", mac_addr, request.body)
    try:
        data_request = json.loads(request.body.decode())
    except json.JSONDecodeError:
        LOGGER.info("Invalid Murata calibration data: %s %s", mac_addr, request.body)
    device_id = data_request.get('name', None)
    old_pars = None
    if 'pars' in data_request:
        old_pars = data_request['pars'].split(',')
        LOGGER.info("Murata: old parameters = %s", data_request['pars'])

    data_save = {"action": "calibrate",
                 "device_id": device_id,
                 "pars_old": old_pars,
                 "body": request.body.decode()}

    if device_id is not None:
        device = models.Device.get_by_secret_id(device_id)
        pars_new = device.attrs.get('pars_new', None)
        if pars_new is not None:
            pars_new = json.loads(pars_new)

    response = { }

    # Parameters are: 0=var_level_1, 1=var_level_2, 2=stroke_vol, 3=tentative_stroke_vol, 4=signal_range, 5=to_micro_g
    #pars = [6000, 300, 4000, 1500,  7]    # our standard params
    #pars = [7000, 270, 5000, 0, 1400, 7]   # in Murata docs
    if pars_new is not None:
        if len(pars_new) != 7:
            raise ValueError("Wrong number of Murata parameters: %s"%pars_new)
        response['pars'] = ','.join(str(_) for _ in pars_new)
        LOGGER.info("Murata: pars_new = %s", response['pars'])
        data_save['pars_new'] = pars_new

    # Save data outside of trasaction.
    save_data(data=json.dumps(data_save), device_id=device_id,
              request=request)
    # Finalize in transaction.  Update parameters and save data.
    if device_id is not None:
        with transaction.atomic():
            device.attrs['pars_old'] = json.dumps(old_pars)
            device.attrs['pars_old_received_ts'] = timezone.now().timestamp()
            if pars_new is not None:
                del device.attrs['pars_new']
                device.attrs['pars_new_sent_ts'] = timezone.now().timestamp()

    return JsonResponse(response)
