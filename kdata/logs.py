

from . import models

import logging

logger = logging.getLogger('kdata.datalog')


def log(request, message, user=None,
        obj=None, op=None,
        data_of=None,
        duration=None,
):
    user = request.user
    username = user.username
    ip = request.META.get('REMOTE_ADDR', None)

    logger.info('%s %s %s?%s o=%s op=%s u=%s data_of=%s "%s"'%(
        request.get_host(),
        request.method, request.path, request.META['QUERY_STRING'],
        obj, op,username,
        data_of.username if data_of is not None else '',
        message))
