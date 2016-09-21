"""Twitter scraping support for Koota.


API terms: https://dev.twitter.com/overview/terms/agreement-and-policy

TODO:
- unlink
- handle invalid tokens
- handle rate limit exceeded

"""

from datetime import timedelta
from json import dumps, loads
import time

from django.conf import settings
from django.conf.urls import url, include
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect, Http404
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from requests_oauthlib import OAuth1Session

from .. import converter
from .. import devices
from .. import exceptions
from .. import logs
from .. import models
from .. import permissions
from .. import util
from .. import views



import logging
logger = logging.getLogger(__name__)



client_key = settings.TWITTER_KEY
client_secret = settings.TWITTER_SECRET
request_token_url = 'https://api.twitter.com/oauth/request_token'
base_authorization_url = 'https://api.twitter.com/oauth/authorize'
access_token_url = 'https://api.twitter.com/oauth/access_token'
API_BASE = 'https://api.twitter.com/1.1/%s.json'

@devices.register_device(default=False, aliases=['kdata.twitter.Twitter'])
class Twitter(devices.BaseDevice):
    dbmodel = models.OauthDevice
    converters = devices.BaseDevice.converters + [
        converter.JsonPrettyHtmlData,
                 ]
    config_instructions_template = """
Current state: {{device.oauthdevice.state}}.
<ul>
    {% if device.oauthdevice.state != 'linked' %}
      <li>Please link this
        <form method="post" style="display: inline" action="{% url 'twitter-link' public_id=device.public_id %}">{%csrf_token%}
        <button type="submit" class="btn btn-xs">here</button>
        </form>
    </li>
    {% endif %}
    {% if device.oauthdevice.state == 'linked' %}
      <li>If desired, you may unlink the device here:
      <form method="post" style="display: inline" action="{% url 'twitter-unlink' public_id=device.public_id %}">{%csrf_token%}
      <button type="submit" class="btn btn-xs">here</button>
      </form>
    </li>
    {% endif %}
</ul>
"""
    @classmethod
    def create_hook(cls, instance, user):
        super(Twitter, cls).create_hook(instance, user)
        instance.state = 'unlinked'
        instance.save()


@login_required
@require_http_methods(["POST"])
def link(request, public_id):
    """Step one of linking the device
    """
    device = models.OauthDevice.get_by_id(public_id)
    if not permissions.has_device_config_permission(request, device):
        raise exceptions.NoDevicePermission("No permission for device")
    # TODO: error handling
    callback_uri = request.build_absolute_uri(reverse(done))

    # 1: Request tokens
    session = OAuth1Session(client_key,
                            client_secret=client_secret,
                            callback_uri=callback_uri,
    )
    fetch_response = session.fetch_request_token(request_token_url,
                                           )
    #{
    #    "oauth_token": "Z6eEdO8MOmk394WozF5oKyuAv855l4Mlqo7hhlSLik",
    #    "oauth_token_secret": "Kd75W4OQfb2oJTV0vzGzeXftVAwgMnEK9MumzYcM"
    #}
    # These are the request tokens.
    resource_owner_key = fetch_response.get('oauth_token')
    resource_owner_secret = fetch_response.get('oauth_token_secret')

    device.request_key = resource_owner_key
    device.request_secret = resource_owner_secret
    device.save()
    logs.log(request, 'Twitter: begin linking',
             obj=device.public_id, op='link_begin')


    authorization_url = session.authorization_url(base_authorization_url)
    #print 'Please go here and authorize,', authorization_url
    return HttpResponseRedirect(authorization_url)

@login_required
def done(request):
    # Same as in link function above.
    session = OAuth1Session(client_key,
                            client_secret=client_secret,
                            #callback_uri="http://localhost:8002/twitter/done/"
    )


    #redirect_response = raw_input('Paste the full redirect URL here: ')
    #oauth_response = oauth.parse_authorization_response(redirect_response)
    redirect_response = request.build_absolute_uri()
    # http://127.0.0.1/twitter/done/?oauth_token=iTy7NwAAAAAAvEjNAAABVMVlcmo&oauth_verifier=kdPz02n5sFqryMfco0dI2i02P1HOyT2v
    oauth_response = session.parse_authorization_response(redirect_response)
    #{
    #    "oauth_token": "Z6eEdO8MOmk394WozF5oKyuAv855l4Mlqo7hhlSLik",
    #    "oauth_verifier": "sdflk3450FASDLJasd2349dfs"
    #}
    verifier = oauth_response.get('oauth_verifier')

    device = models.OauthDevice.objects.get(request_key=oauth_response['oauth_token'])
    if not permissions.has_device_config_permission(request, device):
        raise exceptions.NoDevicePermission("No permission for device")
    resource_owner_key = device.request_key
    resource_owner_secret = device.request_secret

    # 3: get access tokens
    session = OAuth1Session(client_key,
                            client_secret=client_secret,
                            resource_owner_key=resource_owner_key,
                            resource_owner_secret=resource_owner_secret,
                            verifier=verifier)
    oauth_tokens = session.fetch_access_token(access_token_url)
    #{
    #    "oauth_token": "6253282-eWudHldSbIaelX7swmsiHImEL4KinwaGloHANdrY",
    #    "oauth_token_secret": "2EEfA6BG3ly3sR3RjE0IBSnlQu4ZrUzPiYKmrkVU"
    #}
    resource_owner_key = oauth_tokens.get('oauth_token')
    resource_owner_secret = oauth_tokens.get('oauth_token_secret')

    # save these
    device.resource_key = resource_owner_key
    device.resource_secret = resource_owner_secret
    device.ts_linked = timezone.now()
    device.state = 'linked'
    device.save()
    logs.log(request, 'Twitter: done linking',
             obj=device.public_id, op='link_done')
    # redirect user back to place they belong
    target = reverse('device-config',
                      kwargs=dict(public_id=device.public_id))
    if 'login_view_name' in request.session:
        target = reverse(request.session['login_view_name'])
    return HttpResponseRedirect(target)


@login_required
@require_http_methods(["POST"])
def unlink(request, public_id):
    # Destroy the auth tokens
    device = models.OauthDevice.get_by_id(public_id)
    if not permissions.has_device_config_permission(request, device):
        raise exceptions.NoDevicePermission("No permission for device")
    device.state = 'unlinked'
    device.resource_key = ''
    device.resource_secret = ''
    device.data = dumps(dict(unlinked=time.ctime()))
    device.save()
    logs.log(request, 'Twitter: unlink',
             obj=device.public_id, op='unlink')
    # redirect user back to place they belong
    target = reverse('device-config',
                      kwargs=dict(public_id=device.public_id))
    if 'login_view_name' in request.session:
        target = reverse(request.session['login_view_name'])
    return HttpResponseRedirect(target)





def cursor_get(func, params):
    i = 0
    next_cursor = None
    while True:
        data = func(params)
        yield data
        if data['next_cursor'] == 0:
            break
        # Two tests to ensure we don't go go too far/overload
        if data['next_cursor'] == next_cursor:
            raise
        if i > 15:
            raise
        params['cursor'] = next_cursor = data['next_cursor']



def scrape_device(device_id, save_data=False, debug=False):
    use_last_id = True    # check the last_id, if False then get all data
    use_ratelimit = True  # check the last fetched ts, if False then always proceed
    # Get basic parameters
    device = models.OauthDevice.get_by_id(device_id)
    # Check token expiry
    if device.ts_refresh and device.ts_refresh < timezone.now() + timedelta(seconds=60):
        logger.error('Facebook token expired')
        return
    # Avoid scraping again if already done, and if we are in save_data mode.
    if save_data and use_ratelimit:
        if (device.ts_last_fetch
             and (timezone.now() - device.ts_last_fetch < timedelta(hours=1))):
            return
        device.ts_last_fetch = timezone.now()
        device.save()
    resource_owner_key = device.resource_key
    resource_owner_secret = device.resource_secret

    # Create base OAuth session to use for everything
    session = OAuth1Session(client_key,
                            client_secret=client_secret,
                            resource_owner_key=resource_owner_key,
                            resource_owner_secret=resource_owner_secret)

    def get_twitter(endpoint, params={}, filter_json=lambda j: j,
                    removed_fields=None, allowed_fields=None,
                    since_id_key=None):
        url = API_BASE%endpoint
        all_data = [ ]
        params = { k:v for k,v in params.items() if v is not None }
        # Handle since_id.  If given since_id_key, use this to get the
        # most recent id on the last data-saving run, and save this
        # for use next time.
        if save_data and since_id_key is not None and use_last_id:
            since_id = device.attrs.get('last-id-'+since_id_key)
            if debug:
                print('since_id:', since_id)
            if since_id is not None:
                params['since_id'] = int(since_id)
        # Loop for paging
        while True:
            r = session.get(url, params=params)
            body = r.text
            j = r.json()
            if debug:
                print("="*10)
                print("GET {} {}".format(url, params))
                print("{} {} len={}".format(r.status_code, r.reason, len(r.content)))
                print('  Rate limit:', r.headers['X-Rate-Limit-Limit'],
                      r.headers['X-Rate-Limit-Remaining'])
            # Rate limiting?
            if r.status_code == 429:
                print('RATE LIMIT EXCEEDED: %s: twitter %s: %s'%(r.status_code, endpoint, body))
                raise RuntimeError('Twitter rate limit exceeded')
            # Other errors
            if not r.ok:
                print("Error: {}".format(j['error']))
                print('%s: twitter %s: %s'%(r.status_code, endpoint, body))
                return

            # Handle privacy-preserving functions
            j = filter_json(j)
            util.filter_allowed(j, allowed_fields)
            util.filter_removed(j, removed_fields)
            all_data.append(j)
            if debug:
                print(dumps(j, indent=4, sort_keys=True, separators=(',', ': ')))

            # Create our data storage object and do the storage
            data = dict(endpoint=endpoint,
                        url=url,
                        data=dumps(j),
                        params=params,
                        status_code=r.status_code,
                        reason=r.reason,
                        timestamp=time.time(),
                        version=1,
                    )
            if save_data:
                views.save_data(dumps(data), device.device_id, )
            # Page (start the loop again) if necessary.
            if 'next_cursor' in j and j['next_cursor'] != 0:
                params['cursor'] = j['next_cursor']
                continue
            break
        # Store our most recent tweet, for use in filtering the next
        # time around.
        if save_data and since_id_key is not None and all_data[-1] and use_last_id:
            device.attrs['last-id-'+since_id_key] = max(x['id'] for x in all_data[-1])
        return all_data

    def filter_json(j):
        if not isinstance(j, list):
            return j
        for row in j:
            if 'text' in row:
                row['text_len'] = len(row['text'])
                row['text'] = None
        return j


    # Get user object to get screen name and user ID
    #settings_url = API_BASE%'account/settings'
    ret = get_twitter('account/verify_credentials',
                      {'skip_status':True},
                      filter_json=filter_json,
                      #removed_fields={'description'}
                          )
    #print(ret, '\n')
    screen_name = ret[0]['screen_name']
    #user_id = ret[0]['id']


    ret = get_twitter('statuses/user_timeline',
                      params={'screen_name':screen_name,
                              #'since_id':last_id,
                              'include_rts':'false'},
                      since_id_key='user-timeline',
                      filter_json=filter_json,
                      allowed_fields=['created_at', 'favorite_count', 'id',
                                      'in_reply_to_user_id', 'retweet_count',
                                      'favourites_count', 'follow_request_sent',
                                      'followers_count', 'friends_count',
                                      'listed_count', 'protected',
                                      'statuses_count',  #in user{}
                                      'user_mentions','id' #of the user mentions
                                      ])

    ret = get_twitter('statuses/mentions_timeline',
                      params={#'since_id':1442260740,
                              'trim_user':1},
                      since_id_key='menitions-timeline',
                      filter_json=filter_json,
                      allowed_fields=['created_at', 'favorite_count', 'id',
                                      'in_reply_to_status_id', 'in_reply_to_user_id',
                                      'retweet_count', 'user', 'endpoint',
                                      'params:{"since_id"}','timestamp'])

    ret = get_twitter('statuses/retweets_of_me',
                      params={#'since_id':1442260740,
                              'trim_user':1,
                              'include_entities':'false',
                              'include_user_entities':'false'},
                      since_id_key='retweets-of-me',
                      filter_json=filter_json,
                      allowed_fields=['id', 'retweet_count', 'favorite_count',
                                      'endpoint', 'timestamp'])

    ret = get_twitter('direct_messages/sent',
                      {#'since_id':1442260740,
                       'include_entities':'false'},
                      since_id_key='direct-messages-sent',
                      filter_json=filter_json,
                      # TODO: allowed_fields
                      )

    ret = get_twitter('direct_messages',
                      params={#'since_id':1442260740,
                              'include_entities':'false',
                              'skip_status':1},
                      since_id_key='direct-messages-received',
                      filter_json=filter_json,
                      # TODO: allowed_fields
                      )

    ret = get_twitter('friendships/no_retweets/ids',
                      params={},
                      filter_json=filter_json
                      # TODO: allowed_fields
                      )

    ret = get_twitter('friends/ids',
                      params={'count':5000},
                      filter_json=filter_json,
                      allowed_fields=['ids', 'endpoint', 'timestamp'])

    ret = get_twitter('followers/ids',
                      params={'count':5000},
                      filter_json=filter_json,
                      allowed_fields=['ids', 'endpoint', 'timestamp'])

    ret = get_twitter('friendships/incoming',
                      params={},
                      filter_json=filter_json,
                      # TODO: allowed_fields
                      )

    ret = get_twitter('friendships/outgoing',
                      params={},
                      filter_json=filter_json,
                      # TODO: allowed_fields
                      )

    ret = get_twitter('blocks/ids',
                      params={},
                      filter_json=filter_json,
                      # TODO: allowed_keys
                      )

    ret = get_twitter('lists/ownerships',
                      filter_json=filter_json,
                      allowed_fields=['created_at', 'id', 'member_count', 'mode',
                                      'subscriber_count','endpoint','timestamp'])

    ret = get_twitter('lists/subscriptions',
                      filter_json=filter_json,
                      allowed_fields=['lists', 'endpoint', 'timestamp'])


    #import IPython ; IPython.embed()


def scrape_all(save_data=False, debug=False):
    devices_ = Twitter.dbmodel.objects.filter(type=Twitter.pyclass_name(),
                                             state='linked')
    for device in devices_:
        print(device)
        scrape_device(device.device_id, save_data=save_data, debug=debug)

Twitter.scrape_one_function = staticmethod(scrape_device)
Twitter.scrape_all_function = staticmethod(scrape_all)




urlpatterns = [
    url(r'^link/(?P<public_id>[0-9a-f]+)$', link, name='twitter-link'),
    url(r'^done/$', done, name='twitter-done'),
    url(r'^unlink/(?P<public_id>[0-9a-f]+)$', unlink, name='twitter-unlink'),
]
