# https://developers.facebook.com/docs/facebook-login/manually-build-a-login-flow

"""Facebook scraping support for Koota.

TODO:
- unlink
- token expiry and renewal
- handle declined permissions
- enable server-to-server signing
- handle required policy
"""

import base64
from datetime import timedelta
import hmac
from json import dumps, loads
import os
import time
import urllib.parse

from django.conf import settings
from django.conf.urls import url, include
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect, Http404
from django.utils import timezone
from django.views.decorators.http import require_http_methods

import requests
from requests_oauthlib import OAuth2Session
from requests_oauthlib.compliance_fixes import facebook_compliance_fix

from . import converter
from . import devices
from . import logs
from . import models
from . import permissions
from . import views



import logging
logger = logging.getLogger(__name__)



FACEBOOK_ID = settings.FACEBOOK_KEY
FACEBOOK_SECRET = settings.FACEBOOK_SECRET
FACEBOOK_REDIRECT_URLDOMAIN = settings.FACEBOOK_REDIRECT_URLDOMAIN
FACEBOOK_DONE_DOMAINS = settings.FACEBOOK_DONE_DOMAINS
app_access_token = '%s|%s'%(FACEBOOK_ID, FACEBOOK_SECRET)
fb_permissions = settings.FACEBOOK_PERMISSIONS

authorization_base_url = 'https://www.facebook.com/dialog/oauth'
token_url = 'https://graph.facebook.com/v2.3/oauth/access_token'
API_BASE = 'https://graph.facebook.com/v2.7/%s'




@devices.register_device_decorator(default=False)
class Facebook(devices.BaseDevice):
    dbmodel = models.OauthDevice
    converters = devices.BaseDevice.converters + [
        converter.JsonPrettyHtmlData,
                 ]
    config_instructions_template = """
Current state: {{device.oauthdevice.state}}.
<ul>
    {% if device.oauthdevice.state != 'linked' %}
      <li>Please link this
        <form method="post" style="display: inline" action="{% url 'facebook-link' public_id=device.public_id %}">{%csrf_token%}
        <button type="submit" class="btn btn-xs">here</button>
        </form>
    </li>
    {% endif %}
    {% if device.oauthdevice.state == 'linked' %}
      <li>If desired, you may unlink the device here:
      <form method="post" style="display: inline" action="{% url 'facebook-unlink' public_id=device.public_id %}">{%csrf_token%}
      <button type="submit" class="btn btn-xs">here</button>
      </form>
    </li>
    {% endif %}
</ul>
"""
    @classmethod
    def create_hook(cls, instance, user):
        super(Facebook, cls).create_hook(instance, user)
        instance.state = 'unlinked'
        instance.save()


def gen_callback_uri(request, device):
    """Generate callback URI.  Must be done in two places and must be identical"""
    if FACEBOOK_REDIRECT_URLDOMAIN is None:
        callback_uri = request.build_absolute_uri(reverse(done))
    else:
        callback_uri = urllib.parse.urljoin(FACEBOOK_REDIRECT_URLDOMAIN, reverse(done))
    return callback_uri



def gen_proof(access_token):
    return hmac.new(FACEBOOK_SECRET.encode('ascii'),
                    access_token.encode('ascii'), 'sha256').hexdigest()
class FacebookAuth(requests.auth.AuthBase):
    """Requests auth for Instagram signing

    https://www.instagram.com/developer/secure-api-requests/

    Sort parameters, create '/endpoint|param1=v|param2=v' with sorted
    params and hmac-sha256.
    """
    def __init__(self, access_token):
        self.access_token = access_token
        self.appsecret_proof = hmac.new(FACEBOOK_SECRET.encode('ascii'), access_token.encode('ascii'), 'sha256').hexdigest()
    def __call__(self, r):
        if r.method.upper() == 'GET':
            # Get required data
            url = urllib.parse.urlparse(r.url)
            qs = urllib.parse.parse_qsl(url.query)
            # Add tokens
            qs_new = qs + [('access_token', self.access_token),
                           ('appsecret_proof', self.appsecret_proof)]
            # Reassemble the request
            qs_new = urllib.parse.urlencode(qs_new)
            url_new = url._replace(query=qs_new)
            r.url = url_new.geturl()
            #import IPython ; IPython.embed()
        elif r.method.upper() == 'POST':
            # Get required data
            url = urllib.parse.urlparse(r.url)
            qs = urllib.parse.parse_qsl(r.body)
            # Add tokens
            qs_new = qs + [('access_token', self.access_token),
                           ('appsecret_proof', self.appsecret_proof)]
            # reassemble body
            qs_new = urllib.parse.urlencode(qs_new)
            r.body = qs_new
        else:
            raise NotImplementedError()
        return r



@login_required
@require_http_methods(["POST"])
def link(request, public_id):
    """Step one of linking the device
    """
    device = models.OauthDevice.get_by_id(public_id)
    if not permissions.has_device_config_permission(request, device):
        raise exceptions.NoDevicePermission("No permission for device")
    # TODO: error handling
    callback_uri = gen_callback_uri(request, device)
    scope = ','.join(fb_permissions)

    # Also encode the domain in the state, since we need to redirect
    # back to it.  Facebook is not as flexible in the allowed callback
    # domains.  This allows us to redirect back to certain authorized
    # domains for the final step.
    state = base64.urlsafe_b64encode(os.urandom(24)).decode('ascii')
    this_domain = request.get_host()
    state = this_domain + '|||' + state

    # 1: Request tokens
    session = OAuth2Session(FACEBOOK_ID, redirect_uri=callback_uri, scope=scope, state=state)
    session = facebook_compliance_fix(session)

    authorization_url, state = session.authorization_url(authorization_base_url)
    # authorization_url = https://www.facebook.com/dialog/oauth?response_type=code&client_id=FACEBOOK_ID&redirect_uri=CALLBACK_URI&state=XXXXXXX
    # state = XXXXXXX

    # save state
    device.request_key = state
    device.save()
    logs.log(request, 'Facebook: begin linking',
             obj=device.public_id, op='link_begin')

    return HttpResponseRedirect(authorization_url)



@login_required
def done(request):
    # TODO: handle error: error_reason=user_denied
    #                     &error=access_denied
    #                     &error_description=The+user+denied+your+request.
    if 'error' in request.GET:
        raise exceptions.BaseMessageKootaException("Error in facebook linking: %s"%request.GET, message="An error linking occured")

    #request.GET = QueryDict({'code': ['xxxxxxxx'],  'state': ['xxxxxxx']})
    code = request.GET['code']
    state = request.GET['state']

    # Redirect to sub-project domain, if needed.  This must be safe
    # because the state token could be spoofed!  We have explicit
    # whitelist of domains.
    if '|||' in state:
        redirect_domain = state.split('|||', 1)[0]
        if (redirect_domain != request.get_host()
              and redirect_domain in FACEBOOK_DONE_DOMAINS):
            url = urllib.parse.urlparse(request.build_absolute_uri())
            if 'localhost' in redirect_domain:
                url = url._replace(scheme='http')
            url = url._replace(netloc=redirect_domain)
            return HttpResponseRedirect(url.geturl())

    # Get device object
    device = models.OauthDevice.objects.get(request_key=state)
    if not permissions.has_device_config_permission(request, device):
        raise exceptions.NoDevicePermission("No permission for device")
    callback_uri = gen_callback_uri(request, device)

    # This was the requests-oauthlib way, but it did not work that well.
    # redirect_response = raw_input('Paste the full redirect URL here:')
    #redirect_response = request.build_absolute_uri()
    #rr2 = 'https'+redirect_response[4:]
    #
    #session = OAuth2Session(FACEBOOK_ID, redirect_uri=callback_uri)
    #session = facebook_compliance_fix(session)
    #
    #session.fetch_token(token_url, client_secret=FACEBOOK_SECRET,
    #                    # requests-oauthlib uses
    #                    # authorization_response= instead of code=.
    #                    #authorization_response=redirect_response,
    #                    #authorization_response=rr2,
    #                    code=code,
    #                    #method='GET',
    #                    )
    #
    #access_token = session.access_token

    session = requests.Session()
    r = session.get('https://graph.facebook.com/oauth/access_token',
                    params=dict(client_id=FACEBOOK_ID,
                                redirect_uri=callback_uri,
                                client_secret=FACEBOOK_SECRET,
                                code=code))
    if r.status_code != 200:
        raise exceptions.BaseMessageKootaException("Error in facebook linking: %r %s"%(r, r.text), message="An error linking occured")

    data = urllib.parse.parse_qs(r.text)
    access_token = data['access_token'][0]  # 0 because parse_qs returns list
    expires_in_seconds = float(data['expires'][0])
    now = timezone.now()
    expires_at = now + timedelta(seconds=expires_in_seconds)

    #session.get('https://graph.facebook.com/debug_token', params=dict(input_token=access_token))
    #S2 = requests.Session()
    #r2 = S2.get('https://graph.facebook.com/debug_token', params=dict(input_token=access_token, access_token=FACEBOOK_ID+'|'+FACEBOOK_SECRET))
    #S3 = OAuth2Session(FACEBOOK_ID)
    #S3.get('https://graph.facebook.com/debug_token', params=dict(input_token=access_token, access_token=FACEBOOK_ID+'|'+FACEBOOK_SECRET))


    #return()
    # save these
    #device.resource_key = resource_owner_key
    device.resource_secret = access_token
    device.ts_linked = timezone.now()
    device.ts_refresh = expires_at
    device.state = 'linked'
    device.save()
    logs.log(request, 'Facebook: linking done',
             obj=device.public_id, op='link_done')
    return HttpResponseRedirect(reverse('device-config',
                                        kwargs=dict(public_id=device.public_id)))


@login_required
@require_http_methods(["POST"])
def unlink(request, public_id):
    # Destroy the auth tokens
    device = models.OauthDevice.get_by_id(public_id)
    if not permissions.has_device_config_permission(request, device):
        raise exceptions.NoDevicePermission("No permission for device")
    device.state = 'unlinked'
    device.resource_secret = ''
    device.data = dumps(dict(unlinked=time.ctime()))
    device.save()
    logs.log(request, 'Facebook: unlink',
             obj=device.public_id, op='unlink')
    return HttpResponseRedirect(reverse('device-config',
                                        kwargs=dict(public_id=device.public_id)))




def scrape_device(device_id, save_data=False, debug=False):
    # Get basic parameters
    device = models.OauthDevice.get_by_id(device_id)
    # Check token expiry
    if device.ts_refresh < timezone.now() + timedelta(seconds=60):
        logger.error('Facebook token expired')
        return
    # Avoid scraping again if already done, and if we are in save_data mode.
    if save_data:
        if (device.ts_last_fetch
            and (timezone.now() - device.ts_last_fetch < timedelta(hours=1))):
            return
        device.ts_last_fetch = timezone.now()
        device.save()
    access_token = device.resource_secret

    # Create base OAuth session to use for everything
    session = requests.Session()
    session.auth = FacebookAuth(access_token)

    # Get the permissions we have:
    r = requests.get(API_BASE%'debug_token', {'input_token':access_token},
                     auth=FacebookAuth(app_access_token))
    if debug:
        print(dumps(r.json(), indent=4, sort_keys=True))
    # Result:
    #     {'data': {'scopes': ['user_likes', 'user_friends',
    #     'public_profile'], 'app_id': '1026272630802129', 'issued_at':
    #     1469623396, 'user_id': '119855341788312', 'application': 'Koota
    #     Dev Server', 'is_valid': True, 'expires_at': 1474807396}}
    fb_permissions = r.json()['data']['scopes']


    def get_facebook(endpoint, params={},
                     allowed_fields=None,
                     remove_fields=None,
                     filter_json=lambda j: j):
        """Function to get and save data from one API call.

        - This handles paging, saving multiple data packets in that
          case (TODO: should it combine them?)

        - `filter_json`: If given, this function is applied to the
          JSON response and can make any changes to remove sensitive
          data.

        - `allowed_keys`: If given, should be an iterable of keys.
          Only these keys will be saved from the data.

        - `remove_keys`: If given, should be an iterable of keys.
          These will be removed from the data.

        - TODO: if paged, data is in data[]

        """
        url = API_BASE%endpoint
        all_data = [ ]
        count = 0
        if allowed_fields is not None:
            params = params.copy()
            params['fields'] = ','.join(allowed_fields)
        #params['debug'] = 'all' # j['__debug__'] in response
        #params['debug'] = 'warning'
        # Loop is to handle paging
        while True:
            count += 1
            if debug: print("GET", url, params if params else '')
            if debug and count > 1: print("  request index: %s"%count)
            # Get the data
            r = session.get(url, params=params)
            body = r.text
            j = r.json()
            if debug:
                print("{} {} len={}".format(r.status_code, r.reason, len(r.content)))
                print(dumps(j, indent=4, sort_keys=True, separators=(',', ': ')))
            # Rate limit?
            if 'X-App-Usage' in r.headers:
                print(r.headers['X-App-Usage'])
            # Handle error cases
            if not r.ok or 'error' in j:
                print("Error: {}".format(j['error']))
            # Handle privacy-preserving functions.
            j = filter_json(j)
            all_data.append(j)
            if remove_fields is not None:
                for field in remove_fields:
                    j.pop(j, None)
            # Create our data storage object and do the storage.
            data = dict(endpoint=endpoint,
                        url=url,
                        data=dumps(j),
                        params=params,
                        status_code=r.status_code,
                        reason=r.reason,
                        timestamp=time.time(),
                        version=1,
                    )
            #if debug:
            #    print(dumps(data, indent=4, sort_keys=True, separators=',:'))
            if save_data:
                views.save_data(dumps(data), device.device_id, )
            # Page (start the loop again) if necessary.
            if 'paging' in j and 'next' in j['paging']:
                url = j['paging']['next']
                # explicit continue here, break by default for safety
                continue
            break
        return all_data


    get_facebook('me',
                 allowed_fields=('id',
                                 'about',
                                 'age_range',
                                 'birthday',
                                 'gender',
                                 'languages'))
    get_facebook('me/friends',
                 allowed_fields="id",
                 )
    get_facebook('me/friendlists')


    #import IPython ; IPython.embed()


def scrape_all(save_data=False, debug=False):
    devices = Facebook.dbmodel.objects.filter(type=Facebook.pyclass_name(),
                                              state='linked')
    for device in devices:
        print(device)
        scrape_device(device.device_id, save_data=save_data, debug=debug)

Facebook.scrape_one_function = staticmethod(scrape_device)
Facebook.scrape_all_function = staticmethod(scrape_all)




urlpatterns = [
    url(r'^link/(?P<public_id>[0-9a-f]+)$', link, name='facebook-link'),
    url(r'^unlink/(?P<public_id>[0-9a-f]+)$', unlink, name='facebook-unlink'),
    url(r'^done/$', done, name='facebook-done'),
]
