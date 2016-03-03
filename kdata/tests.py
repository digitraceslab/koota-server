from django.test import TestCase, Client

# Create your tests here.

from django.test import TestCase
from kdata import models

class p:
    def __sub__(self, other): print(other)
p = p()


class BasicTest(TestCase):
    def setUpTestData():
        pass
    def setUp(self):
        user = models.User.objects.create_user('test-user', 'test@example.com',
                                               'test2')
        user.save()

    def test_basic(self):
        c = self.client
        c.get('/')
        c.get('/login/')
        r = c.post('/login/', {'username': 'test-user', 'password': 'test2'})
        p- r.status_code
        c.login(username='test-user', password='test2')
        r = c.get('/')
        self.assertContains(r, 'test-user')
        r = c.get('/devices/')
        r = c.post('/devices/create/', dict(type='PurpleRobot', name='test-device-150'))
        p- r.url
        #import IPython; IPython.embed()
        r = c.get('/devices/')

