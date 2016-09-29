"""Base classes for devices.
"""
import six

from .. import converter
from .. import models
from .. import util

import logging
logger = logging.getLogger(__name__)


# Here we define the different types of available devices.  This is
# sort of tricky.  For models.Device, we need Device.type.choices to
# have *all* possible devices, otherwise the DB won't validate.
# However, we need to restrict the types of devices available in
# forms, because sometimes some devices will only be available to
# certain users.
# Standard device choices: What should always be in forms.
standard_device_choices = [ ]
# All device choices: what should validate in DB.
all_device_choices = [('PurpleRobot', "Purple Robot") ]
# All registered devices.  Used as an efficient lookup to see what
# needs to be found.
#registered_devices = { }
# This is used to remap short names to classes.
device_class_lookup = { }
# List with each actual class object.
all_device_classes = [ ]

def get_choices(all=False):
    """Get the device classes.

    all=False --> return standard for forms.
    all=True  --> return all for DB."""
    if all:
        return list(x[:2] for x in all_device_choices)
    return list(x[:2] for x in standard_device_choices)
def _register_device(cls, desc=None, default=False,
                    alias=None, aliases=None):
    """Allow us to dynamically register devices.

    This dynamically changes the models.Device.type.choices when
    things are registered.  It is a hack but can be improved later...

    cls: class to register
    description: human description of class (for django form fields).
                 If not given, use cls.desc.
    default: if true, this device will be available to all users by
             default.
    alias: if given, this short name will be used in the database,
           instead of the full importable name.
    """
    # device_class_lookup is a table of all devices and device names.
    name = cls.pyclass_name()
    device_class_lookup[name] = cls
    if alias is not None:
        name = alias
    device_class_lookup[name] = cls
    if aliases:
        for alias_ in aliases:
            device_class_lookup[alias_] = cls
    # description: description in the form field
    if desc is None:
        desc = getattr(cls, 'desc', cls.name())
    # The actula django choices tuple
    row = name, desc
    # Add it to list of all possible device choices
    all_device_choices.append(row)
    #registered_devices[name] = cls  # TODO: use this for lookups!
    all_device_classes.append(cls)
    if default:
        standard_device_choices.append(row)
    # This is an epic hack and deserves fixing eventually.  We must
    # extend the model fields, or else updated models won't pass
    # validation.  Eventually, devices should not be a .choices
    # property on a model.

    # Second hack: kdata.models and kdata.devices import each other.
    # This needs to have models.Device initialized, but this is not
    # done until after this file is loaded.  So we can't
    # register_device in this file yet.  Here is our hack: if
    # models.Device is not there yet, then don't do anything.  There
    # is a line
    if hasattr(models, 'Device'):
        models.Device._meta.get_field('type').choices \
            = all_device_choices

# Class decorator for the above function
def register_device(desc=None, default=False, alias=None,
                              aliases=None):
    """Register devices (as class decorator)

    Similar signature as register_device()"""
    def register(cls):
        if alias is not None:
            cls._class_alias = alias
        _register_device(cls, desc=desc, default=default, alias=alias,
                        aliases=aliases)
        return cls
    return register



def get_class(name, default=None):
    """Get a device class by (string) name.

    Option 1: from this device_class_lookup
    Option 2: import it, if it contains a '.'.
    Option 3: return generic device BaseDevice.
    """
    if name in device_class_lookup:
        device = device_class_lookup[name]
    else:
        device = util.import_by_name(name, default=BaseDevice)
        if device is BaseDevice:
            logger.warning("Device not found: %s", name)
    return device



# Metaclass for survey device.
class DeviceMetaclass(type):
    """Automatically register new devices

    This metaclass will call devices.register_device automatically
    upon class definition, if the _register_device attribute is True.
    This is an alternative method to the register_device_decorator()
    decorator.

    In the future this could do other automatic setup.
    """
    def __new__(mcs, name, bases, dict):
        cls = type.__new__(mcs, name, bases, dict)
        if (not cls.__name__.startswith('Base')
            and not cls.__name__.startswith('_')
            and getattr(cls, '_register_device', True)
           ):
            _register_device(cls, getattr(cls, 'desc', None),
                            default=cls._register_default)
        return cls


# Basic device class
import random, string
@six.add_metaclass(DeviceMetaclass)
class BaseDevice(object):
    """Standard device object."""
    # if true, then automanically register this device.
    _register_device = False
    _register_default = False
    # This is the canonical name of the device, if not None.
    _class_alias = None
    # Converters are special data processors.
    converters = [converter.Raw,
                  converter.PacketSize]
    # If dbmodel is given, this overrides the models.Device model when
    # an object is created.  This has to be used _before_ the DB
    # device is created, so needs some hack kind of things in forms.
    # This is handleded in kdata.views.DeviceCreate.model().
    dbmodel = None
    # String containing django template to be rendered as the
    # configuration instructions on the device /config page.
    config_instructions_template = None
    # Like above, but a django template filename loaded using the normal means.
    config_instructions_template_file = None

    def __init__(self, dbrow):
        """Bind a DB row to this"""
        self.dbrow = dbrow # new
        self.data = dbrow  # old, deprecated
    @classmethod
    def name(cls):
        """Human name for this device.

        This is used in select fields and so on."""
        return cls.__name__
    @classmethod
    def pyclass_name(cls):
        """Importable name for this class.

        This is the canonical type name of this device, used in the
        database.  It can either be a custom alias, or the importable
        class name.
        """
        if cls._class_alias is not None:
            return cls._class_alias
        return '%s.%s'%(cls.__module__, cls.__name__)
    @classmethod
    def _devicechoices_row(cls):
        """Helper for adding this to device list.

        This returns (pyclass_name, name) that is used for the choices
        option of the "type" field of the model, and selection
        forms.
        """
        return (cls.pyclass_name(), getattr(cls, 'desc', cls.name()))

    @classmethod
    def create_hook(cls, instance, user):
        """Do initial device set-up.

        Create and set the various device_ids.  This was originally in
        kdata/views.py:DeviceCreate, and now other classes can extend
        this.
        """
        # random device ID
        # Loop until we find an ID which does not exist.
        while True:
            id_ = ''.join(random.choice(string.hexdigits[:16]) for _ in range(14))
            id_ = util.add_checkdigits(id_)
            try:
                instance.__class__.get_by_id(id_[:6])
            except instance.DoesNotExist:
                break
        instance.device_id = id_
        instance._public_id = id_[:6]
        instance._secret_id = id_

    @classmethod
    def configure(cls, device):
        """Return any special options for configuration.

        A dict mapping keys to values.  This is used on the
        device_config page.
        """
        return { }
    # Below are the new config protocol
    def config_context(self):
        """Replacement of self.configure().  Does not have to super() anything"""
        context = { }
        if hasattr(self, 'configure'):
            # Old-style config: this sets context['raw_instructions']
            # and there is nothing more that needs to be done.
            context = self.configure(self.dbrow)
        return context
    def get_raw_instructions(self, context=None, request=None):
        """Get raw_instructions string necessary for config() template"""
        if context is None:
            context = { }
            context['device'] = self.data
            context['device_class'] = self

        # Render the template or whatever is needed.  First we try to find a template.
        import django.template
        template = None
        # self.*template_file: load this filename using template loading system
        if self.config_instructions_template_file is not None:
            template = django.template.loader.get_template(
                self.config_instructions_template)
        # self.config_instructions_template: this is the raw template as a string
        elif self.config_instructions_template is not None:
            engine = django.template.engines['django']
            template = engine.from_string(self.config_instructions_template)
        # If we found any template, do the rendering.
        if template is not None:
            text = template.render(context=context, request=request)
            context['raw_instructions'] = text
        return context

    #@classmethod
    #def post(cls, request):
    #    """Handle special options needed for accepting data.
    #
    #    Returns a dict which controls the functioning of the post() view."""
    #    return { }



