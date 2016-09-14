"""Koota's planned Android device, never implemented.
"""

from ..devices import BaseDevice, register_device

@register_device(default=False, alias='Android')
class Android(BaseDevice):
    converters = BaseDevice.converters + [
                  ]
    @classmethod
    def configure(cls, device):
        """Special options for configuration
        """
        return dict(qr=True)
