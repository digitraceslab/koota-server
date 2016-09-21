"""Murata Bed Sensor Node

http://www.murata.com/en-eu/products/sensor/accel/sca10h_11h/sca11h
"""
import json
import logging
import textwrap

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .. import converter
from ..devices import BaseDevice, register_device

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
def murata_calibrate(request, dev_id=None):
    # pyli nt disable=redefined-variable-type,unused-variable
    # BSN syncs its FW version details and BCG calibration parameters
    # with cloud server after power on/reset and then every 24 hours.
    LOGGER.info("Calibrate received: %s %s", dev_id, request.body)
    try:
        data = json.loads(request.body.decode())
    except json.JSONDecodeError:
        LOGGER.info("Invalid data: %s %s", dev_id, request.body)
    if 'pars' in data:
        old_pars = data['pars'].split(',')
        LOGGER.info("Murata: old parameters = %s", old_pars)

    response = { }

    # Parameters are: 0=var_level_1, 1=var_level_2, 2=stroke_vol, 3=tentative_stroke_vol, 4=signal_range, 5=to_micro_g
    pars = None
    #pars = [6000, 300, 4000, 1500,  7]    # our standard params
    #pars = [7000, 270, 5000, 0, 1400, 7]   # in Murata docs
    if pars is not None:
        if len(pars) != 7:
            raise ValueError("Wrong number of Murata parameters: %s"%pars)
        LOGGER.info("Murata: old parameters = %s", old_pars)
        response['pars'] = ','.join(str(_) for _ in pars)

    return JsonResponse(response)
