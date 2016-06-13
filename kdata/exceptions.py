
import base64
import os
import traceback

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
class OtpRequired(BaseMessageKootaException):
    message = "You must enable two-factor authentication first."
class NotImplemented(BaseMessageKootaException):
    message = "This has not been implemented yet."
