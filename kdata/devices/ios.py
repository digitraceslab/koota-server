"""Koota's original iOS device, no longer used.
"""

from .. import converter
from ..devices import BaseDevice, register_device

@register_device(default=False, alias='Ios')
class Ios(BaseDevice):
    desc = "iOS (our app)"
    converters = BaseDevice.converters + [
                  converter.IosProbes,
                  converter.IosTimestamps,
                  converter.IosDataSize,
                  converter.IosRecentDataCounts,
                  converter.IosLocation,
                  converter.IosScreen,
                 ]
    @classmethod
    def configure(cls, device):
        """Special options for configuration
        """
        return dict(qr=True)
