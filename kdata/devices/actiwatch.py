"""Philips Actiwatch
"""
import textwrap
import re

from .. import converter
from ..devices import BaseDevice, register_device


# Create a (horrible) regular expression that will remove various
# identifying information while preserving the structure of the CSV
# file.  The following fields will be removed.
to_remove_keys = ["Identity",
                  "Initials",
                  "Full.Name",
                  "Street.Address",
                  "Country",
                  "Phone",
                  "Gender",
                  "Date.of.Birth",
                  r"of.export.file.creation\)",
                  r"start.of.data.collection\)",

                  "Filename",
                  "Analysis.Name",
                  ]
strip_re = re.compile(rb'((%b):?"?,"?)   [^"$]{1,}   ("?($|,))'%('|'.join(to_remove_keys).encode()),
                          re.M|re.I|re.X)



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

    def process_upload(self, data):
        """When data is uploaded, reprocess it for privacy.

        For Actiwatches, this removes some key identifying fields in the
        data.
        """
        data, n_replacements = strip_re.subn(rb"\1xxxxx\3", data)
        return data
