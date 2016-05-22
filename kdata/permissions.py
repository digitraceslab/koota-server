"""Standard location for all permissions tests"""

import six

from django.http import Http404


from . import models

def has_device_permission(request, device):
    """Test for user having permissions to access device.
    """
    if isinstance(device, six.string_types):
        device = models.Device.objects.get(device_id=device)
    # is_verified tests for 2FA (OTP).
    if request.user.is_superuser and request.user.is_verified():
        return True
    if device.user == request.user:
        return True
    return False



def has_group_researcher_permission(group, user):
    """Test a researcher's permission to access a group's data.
    """
    group_class = group.get_class()
    # If the group requires researchers to use 2FA, deny if they don't
    # have it enabled.
    if group.otp_required and not request.user.is_verified():
        return False
    # We can delegate our logic to the group class, if it defines the
    # is_researcher method.
    if hasattr(group_class, 'is_researcher'):
        if group_class.is_researcher(user):
            return True
        return False
    # Normal test.
    if group.is_researcher(user):
        return True
    # Default deny
    return False
