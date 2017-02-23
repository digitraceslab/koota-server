"""Murata Bed Sensor Node

http://www.murata.com/en-eu/products/sensor/accel/sca10h_11h/sca11h
"""
import json
import logging
import textwrap

from django.db import transaction
from django import forms
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .. import converter
from ..devices import BaseDevice, register_device
from .. import models
from ..views import save_data

LOGGER = logging.getLogger('kdata.devices.muratabsn')

# Aware config forms
class MurataBSNCalibrationForm(forms.Form):
    calibration = forms.CharField(help_text="Calibration to send.  signal_high,signal_low,min_amp,typ_amp,scale,  Use format: N,N,N,N,N")
class MurataBSNCalibrationReceivedForm(forms.Form):
    calibration = forms.CharField(help_text="Most recent calibration received.  Do not edit.")


from defusedxml.ElementTree import fromstring as xml_fromstring
@register_device(default=True, alias='MurataBSN')
class MurataBSN(BaseDevice):
    desc = 'Murata bed sensor'
    config_forms = [{'form':MurataBSNCalibrationForm, 'key': 'calibration'},
                    {'form':MurataBSNCalibrationReceivedForm, 'key': 'calibration_received'}]
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
        return JsonResponse({'error': 'Bad POST data'}, status=400, reason="Bad POST data")
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

    pars_new = None
    if device_id is not None:
        device = models.Device.get_by_secret_id(device_id)
        # Old way: pars_new option.
        pars_new_data = device.attrs.get('pars_new', None)
        if pars_new_data is not None:
            pars_new = json.loads(pars_new_data)
        # New way: using the config forms.  Get the data.
        pars_new_data2 = device.attrs.get('calibration', None)
        if pars_new_data2 is not None:
            pars_new_data2 = json.loads(pars_new_data2)
            if 'calibration' in pars_new_data2:
                # Sanity check/process data.  Split by commas.
                pars_new = pars_new_data2['calibration']
                pars_new = pars_new.split(',')
                pars_new = [ _.strip() for _ in pars_new ]
                # Sanity check: must be five integers.
                if len(pars_new) != 5 and not all(_.isdigit() for _ in pars_new):
                    raise ValueError("Invalid MurataBSN calibration parameters: %r"%(pars_new,))
                # Create actual parameters.  note the extra zero.
                pars_new = pars_new[0:3] + [0] + pars_new[3:5]

    response = { }

    # Murata docs say to include six numbers, while only five are used for our
    # calibration.  The code above makes six out of five, but this hasn't been
    # verified yet.
    # Parameters are: 0=var_level_1, 1=var_level_2, 2=stroke_vol, 3=tentative_stroke_vol, 4=signal_range, 5=to_micro_g
    #pars = [6000, 300, 4000, 1500, 7]      # our standard params
    #pars = [7000, 270, 5000, 0, 1400, 7]   # in Murata docs
    #
    # How to test calibration: curl --data-raw '{"name": "device_secret_id", "pars": "1,2,3,4,5"}' http://localhost:8002/firmware/device/00:00:00:00:00:00/
    if pars_new is not None:
        if len(pars_new) != 6:
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
            device.attrs['calibration_received'] = json.dumps(dict(calibration=','.join(old_pars)))
            if pars_new is not None:
                del device.attrs['pars_new']
                device.attrs['pars_new_sent_ts'] = timezone.now().timestamp()

    return JsonResponse(response)
