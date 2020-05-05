"""Oura ring
"""
import textwrap
import re

from .. import converter
from ..devices import BaseDevice, register_device


@register_device(default=True)
class Oura(BaseDevice):
    desc = "Oura ring"
    converters = BaseDevice.converters + [
                  ]
    raw_instructions = textwrap.dedent("""\
    Write down the "device secret ID" you can see above.

    Upload form <a href="../upload">is here</a>.
    """)
    @classmethod
    def configure(cls, device):
        return dict(raw_instructions=cls.raw_instructions.format(device=device),
                    )

    def process_upload(self, data):
        """When data is uploaded, reprocess it for privacy.

        This different from the converter processing, this phase is done
        during the upload and affects the raw data stored in the
        database.
        """
        #data, n_replacements = strip_re.subn(rb"\1xxxxx\3", data)
        return data
