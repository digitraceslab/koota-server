from django.conf.urls import url, include
from django.contrib import admin
from django.views.generic import TemplateView
from django.contrib.auth import views as auth_views

from kdata import views as kviews
from kdata import views_data
from kdata import views_admin
from kdata import aware
from kdata import devices
from kdata import funf
from kdata import group
from kdata import survey
from kdata import twitter
from kdata import facebook

urlpatterns = [
    url(r'^post/purple/?(?P<device_id>\w+)?/?$', kviews.post, dict(device_class=devices.PurpleRobot),
        name='post-purple'),
    url(r'^post/?(?P<device_id>[A-Fa-f0-9]+)?/?$', kviews.post, name='post'),
    # the Murata bed sensor has a hard-coded POST URL.
    url(r'^data/push/$', kviews.post, dict(device_class=devices.MurataBSN),
        name='post-MurataBSN'),
    url(r'^config$', kviews.config, name='config'),
    url(r'^devices/$', kviews.DeviceListView.as_view(), name='device-list'),
    url(r'^devices/create/$', kviews.DeviceCreate.as_view(),
        name='device-create'),
    url(r'^devices/(?P<public_id>[0-9a-fA-F]*)/config$', kviews.DeviceConfig.as_view(),
        name='device-config'),
    url(r'^devices/(?P<public_id>[0-9a-fA-F]*)/qr.png$', kviews.device_qrcode,
        name='device-qr'),
    url(r'^devices/(?P<public_id>[0-9a-fA-F]*)/$', views_data.DeviceDetail.as_view(),
        name='device'),
    url(r'^devices/(?P<public_id>[0-9a-fA-F]*)/(?P<converter>\w+)\.?(?P<format>[\w-]+)?',
        views_data.device_data,
        name='device-data'),

    url(r'^log$', kviews.log, name='log'),
    url(r'^stats/', views_admin.stats),

    url(r'^survey/take/(?P<token>[\w]*)', survey.take_survey, name='survey-take'),

    # groups
    # /group/
    url(r'^group/$', group.group_join, name='group-join'),
    # /group/name/
    url(r'^group/(?P<group_name>[\w]+)/$', group.group_detail, name='group-detail'),
    # /group/name/converter(.ext)
    url(r'^group/(?P<group_name>[\w]+)/(?P<converter>\w+)\.?(?P<format>[\w-]+)?$',
        group.group_data, name='group-data'),
    # /group/name/converter(.ext)
    url(r'^group/(?P<group_name>[\w]+)/user-create/$',
        group.group_user_create, name='group-user-create'),
    # Subject related
    # /group/name/subjNN/
    url(r'^group/(?P<group_name>[\w]+)/subj(?P<gs_id>[0-9]+)/$',
        group.group_subject_detail, name='group-subject-detail'),
    # /group/name/subjNN/public_id/config
    url(r'^group/(?P<group_name>[\w]+)/subj(?P<gs_id>[0-9]+)/(?P<public_id>[0-9a-f]+)/config/$',
        kviews.DeviceConfig.as_view(), name='group-subject-device-config'),
    # /group/name/subjNN/converter(.ext)         Subject's data
    url(r'^group/(?P<group_name>[\w]+)/subj(?P<gs_id>[0-9]+)/(?P<converter>\w+)\.?(?P<format>[\w-]+)?$',
        group.group_data, name='group-subject-data'),
    # /group/name/subjNN/create/                 Add subject device
    url(r'^group/(?P<group_name>[\w]+)/subj(?P<gs_id>[0-9]+)/create/$',
        kviews.DeviceCreate.as_view(), name='group-subject-device-create'),

    # /group/name/subjNN/public_id/
    #url(r'^group/(?P<group_name>[\w]+)/subj(?P<gs_id>[0-9]+)/(?P<public_id>[0-9a-f]+)/$',
    #    group.GroupSubjectDeviceDetail.as_view(), name='group-subject-device'),
    # /group/name/subjNN/public_id/              Subject's device detail
    #url(r'^group/(?P<group_name>[\w]+)/subj(?P<gs_id>[0-9]+)/(?P<public_id>[0-9a-f]+)/$',
    #    group.GroupSubjectDetail.as_view(), name='group-subject-data'),

    # Funf
    url(r'^funf/config/(?P<device_id>[A-Fa-f0-9]+)?/?$', funf.config_funf, name='funf-journal-config'),
    url(r'^funf/post1/(?P<device_id>[A-Fa-f0-9]+)?/?$', kviews.post,
        dict(device_class=funf.FunfJournal),
        name='funf-journal-post'),

    # Twitter and other social sites
    url(r'^twitter/', include(twitter.urlpatterns)),
    url(r'^facebook/', include(facebook.urlpatterns)),

    # Aware
#    url(r'^aware/', include(aware.urlpatterns)),
    url(r'^(?:(?P<indexphp>index\.php)/)?aware/', include(aware.urlpatterns)),
    url(r'^(?P<indexphp>index\.php)/', include(aware.urlpatterns_fixed)),

    url(r'^$', TemplateView.as_view(template_name='koota/main.html'), name='main'),
    ]
