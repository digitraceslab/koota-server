import hashlib


class PurpleRobot(object):
    post = reverse_lazy('post-purple')
    config = reverse_lazy('config-purple')
    @classmethod
    def configure(cls):
        """Initial device configuration"""
        return dict(post=self.post,
                    config=self.config)
    @classmethod
    def config(cls):
        """/config url data"""
        pass
    @classmethod
    def post(cls, request):
        request.encoding = ''
        data = json.loads(request.POST['json'])
        Operation = data['Operation']
        UserHash = data['UserHash']
        Payload = data['Payload']
        # Check the hash
        m = hashlib.md5()
        # This re-encoding to utf-8 is inefficient, when we originally
        # got raw binary data, is inefficient.  However, django is
        # fully unicode aware, and there is no easy way to tell it to
        # "not decode anything".  So, this is the workaround.
        m.update((UserHash+Operation+Payload).encode('utf-8'))
        checksum = m.hexdigest()
        if checksum != data['Checksum']:
            return HttpResponseBadRequest("Checksum mismatch",
                                    content_type="text/plain")
        #
        store_data = { }
        device_id = UserHash
        data = json.loads(Payload)

        store_data['REMOTE_ADDR'] = request.META['REMOTE_ADDR']

        data_collection.insert_one(store_data)

        # Construct HTTP response that will allow PR to recoginze success.
        status = 'success'
        payload = '{ }'
        checksum = hashlib.md5(status + payload).hexdigest()
        response = HttpResponse(json.dumps(dict(Status='success',
                                                Payload=payload,
                                                Checksum=checksum)),
                                content_type="application/json")

        return dict(data=data,
                    device_id=device_id,
                    response=response)
