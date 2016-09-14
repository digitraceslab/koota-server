"""Philips Actiwatch
"""
import textwrap

from .. import converter
from ..devices import BaseDevice, register_device


@register_device(default=True, aliases=['kdata.devices.Actiwatch'])
class Actiwatch(BaseDevice):
    desc = "Philips Actiwatch"
    converters = BaseDevice.converters + [
        converter.ActiwatchFull,
        converter.ActiwatchStatistics,
        converter.ActiwatchMarkers,
                  ]
    raw_instructions = textwrap.dedent("""\
    Write down the "device secret ID" you can see above.
    """)
    @classmethod
    def configure(cls, device):
        return dict(raw_instructions=cls.raw_instructions.format(device=device),
                    )
