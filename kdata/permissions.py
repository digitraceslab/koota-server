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
def has_device_config_permission(request, device):
    if has_device_permission(request, device):
        return True
    if has_device_manager_permission(request, device):
        return True
    return False



def has_group_researcher_permission(request, group):
    """Test a researcher's permission to access a group's data.
    """
    researcher = request.user
    group_class = group.get_class()
    # is_verified tests for 2FA (OTP).
    if researcher.is_superuser and researcher.is_verified():
        return True
    # If the group requires researchers to use 2FA, deny if they don't
    # have it enabled.
    if group.otp_required and not researcher.is_verified():
        return False
    # We can delegate our logic to the group class, if it defines the
    # is_researcher method.
    if hasattr(group_class, 'is_researcher'):
        if group_class.is_researcher(researcher):
            return True
        return False
    # Normal test.
    if group.is_researcher(researcher):
        return True
    # Default deny
    return False

# Has permission to view/adjust user's devices
has_group_manager_permission = has_group_researcher_permission



def has_device_manager_permission(request, device):
    """Test for user having permissions to access device.
    """
    #import IPython ; IPython.embed()
    researcher = request.user
    subject = device.user
    group = models.Group.objects.filter(
        subjects=subject,
        researchers=researcher,
        managed=True)
    if not group.exists():
        return False
    # If ANY group requires OTP
    if all(g.otp_required for g in group) and not researcher.is_verified():
        return False
    return True

