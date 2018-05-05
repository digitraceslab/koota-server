

from . import django

Backend = django.Backend

def get_device_backend(device):
    """Get the backend of a device"""
    return Backend(device)
def get_backend(name):
    """Get the backend of a certain name"""
    return Backend
