from django.conf import settings
from django.conf.urls import url, include
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.views.generic import TemplateView


from . import views

urlpatterns = [
    # Purple Robot - different API
    url(r'^device/(?P<public_id>[0-9a-fA-F]+)/?$', views.device_detail,
        name='device-detail'),
    url(r'^device/(?P<public_id>[0-9a-fA-F]+)/(?P<converter>\w+)\.?(?P<format>[\w-]+)?',
        views.device_data, name='device-data'),

]
