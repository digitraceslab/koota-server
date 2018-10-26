
import base64
import os
import traceback

from django.urls import reverse_lazy
from django.utils.safestring import mark_safe

import logging
logger = logging.getLogger(__name__)

class BaseKootaException(Exception):
    pass

class BaseMessageKootaException(BaseKootaException):
    log = None
    status = 400
    def __init__(self, message=None, log=None, status=None,
                 *args, **kwargs):
        parent_frame = traceback.extract_stack()[-2]
        self.log_info = "%s:%s:%s"%(parent_frame.filename,
                                    parent_frame.lineno,
                                    parent_frame.name)

        #import IPython ; IPython.embed()
        super(BaseMessageKootaException, self).__init__(*args, **kwargs)
        self.id_ = base64.b32encode(os.urandom(5)).decode('ascii')
        if message:   self.message = message
        if status:    self.status  = status
        if log:       self.log     = log
        if self.log:
            logger.error("%s: %s: (%s) %s", self.id_, self.log_info,
                         self.message, self.log)



class LoginRequired(BaseMessageKootaException):
    message = "You need to log in."
    status = 403
class NoDevicePermission(BaseMessageKootaException):
    message = "You do not have permissions for this device."
    log = "No device permission"
    status = 403
class NoGroupPermission(BaseMessageKootaException):
    message = "You do not have permissions for this group."
    log = "No group permission"
    status = 403
class InvalidDeviceID(BaseMessageKootaException):
    message = "Invalid device ID."
    status= 480
class OtpRequired(BaseMessageKootaException):
    message = "You must sign in with two-factor authentication first before you can view this page."
    @property
    def body(self):
        return mark_safe("""Please <a href="{logout_url}?next={login_url}">log out and log
        in with your 2FA token</a> (Google authenticator).  If you don't have
        one yet, go to <a href="{otp_config_url}">the 2FA page</a> to set it up
        <b>first</b>.""".format(logout_url=reverse_lazy('logout'),
                               login_url=reverse_lazy('login'),
                               otp_config_url=reverse_lazy('otp-config')))

    status = 307
class NotImplemented(BaseMessageKootaException):
    message = "This has not been implemented yet."
