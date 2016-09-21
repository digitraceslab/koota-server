"""Purple Robot: Android sensing

https://tech.cbits.northwestern.edu/purple-robot/
https://github.com/cbitstech/Purple-Robot
"""
import hashlib
import json
import textwrap

from django.http import HttpResponseBadRequest, JsonResponse
from django.urls import reverse_lazy

from .. import converter
from ..devices import BaseDevice, register_device


@register_device(default=True, alias='PurpleRobot')
class PurpleRobot(BaseDevice):
    post_url = reverse_lazy('post-purple')
    config_url = reverse_lazy('config-purple')
    converters = BaseDevice.converters + [
                  converter.JsonPrettyHtml,
                  converter.PRProbes,
                  converter.PRTimestamps,
                  converter.PRScreen,
                  converter.PRBattery,
                  converter.PRBatteryDay,
                  converter.PRWifi,
                  converter.PRBluetooth,
                  converter.PRStepCounter,
                  converter.PRDeviceInUse,
                  converter.PRLocation,
                  converter.PRAccelerometer,
                  converter.PRAccelerometerBasicStatistics,
                  converter.PRAccelerometerFrequency,
                  converter.PRApplicationLaunches,
                  converter.PRRunningSoftware,
                  converter.PRSoftwareInformation,
                  converter.PRAudioFeatures,
                  converter.PRProximity,
                  converter.PRCallState,
                  converter.PRCallHistoryFeature,
                  converter.PRSunriseSunsetFeature,
                  converter.PRLightProbe,
                  converter.PRCommunicationEventProbe,
                  converter.PRCommunicationEventProbeNoNumber,
                  converter.PRCommunicationEventsDay,
                  converter.PRTouchEvents,
                  converter.PRDataSize1Hour,
                  converter.PRDataSize1Day,
                  converter.PRDataSize1Week,
                  converter.PRDataSize,
                  converter.PRMissingData7Days,
                  converter.PRMissingData,
                  converter.PRRecentDataCounts,
                  ]
    @classmethod
    def configure(cls, device):
        """Initial device configuration"""
        from django.conf import settings
        raw_instructions = textwrap.dedent("""\

        <p>See the new instructions at <a href="https://github.com/CxAalto/koota-server/wiki/PurpleRobot">the wiki page</a>.
        Your <tt>device_secret_id</tt> is <tt>{device.secret_id}</tt> and thus your HTTP upload endpoint is <tt>https://{post_domain}{post}/{device.secret_id}</tt> .

        <!--<p>Old instructions are below (see the wiki page instead):</p>

        Please go to settings and set these properties:<p>

        <ul>
        <li>Probes configuration: Enable probes: on, then go through and manually disable every probe, then turn on these:
        <ul><li> Hardware sensor probes: Location (frequency: 30 min), Step counter. </li>
            <li>Device Info&Config: Battery probe, Screen Probe, Device in Use.</li>
            <li>External device probes: Wifi Probe (sampling frequency: every 5 min)</li>
            <li>You may experiment with any other probes you would like, but consider battery usage.</li>
            </ul>
        </li>
        <!-- <li>User ID: {device.device_id}</li> - ->
        <li>User ID: anything, not used</li>
        <li>General data upload settings
            <ul>
            <li>Accept all SSL certificates: false</li>
            <li>HTTP upload endpoint: https://{post_domain}{post}/{device.secret_id}</li>
            <li>Only use wifi connection: true</li>
            </ul>
        </li>
        <li>JSON uploader settings ==> Enable JSON uploader: on</li>
        <li>User identifier: something random, it is not used</li>
        <li>Configuration URL: blank</li>
        <li>Refresh interval: Never</li>
        </ul>-->

        """.format(
            post=str(cls.post_url),
            device=device,
            post_domain=settings.POST_DOMAIN,
            ))
        return dict(post=cls.post_url,
                    config=cls.config,
                    raw_instructions=raw_instructions,
                    )
    @classmethod
    def config(cls, request):
        """/config url data"""
        pass
    @classmethod
    def post(cls, request):
        request.encoding = ''
        data = json.loads(request.POST['json'])
        Operation = data['Operation']
        UserHash = data['UserHash']
        Payload = data['Payload']
        # Check the hash
        m = hashlib.md5()
        # This re-encoding to utf-8 is inefficient, when we originally
        # got raw binary data, is inefficient.  However, django is
        # fully unicode aware, and there is no easy way to tell it to
        # "not decode anything".  So, this is the workaround.
        m.update((UserHash+Operation+Payload).encode('utf-8'))
        checksum = m.hexdigest()
        if checksum != data['Checksum']:
            return HttpResponseBadRequest("Checksum mismatch",
                                    content_type="text/plain")
        #
        #device_id = UserHash
        #data = json.loads(Payload)
        data = Payload

        # Construct HTTP response that will allow PR to recoginze success.
        status = 'success'
        payload = '{ }'
        checksum = hashlib.md5((status + payload).encode('utf8')).hexdigest()
        response = JsonResponse(dict(Status='success',
                                     Payload=payload,
                                     Checksum=checksum),
                                content_type="application/json")

        return dict(data=data,
                    # UserHash is hashed device_id and thus is not
                    # useful to us.  This info must be found some
                    # other way.
                    #device_id=device_id,
                    response=response)
