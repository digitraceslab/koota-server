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
        group = models.Group(slug='test-group', invite_code='groupinvite',
                             name="Test Group")
        group.save()

    def test_registration(self):
        c = self.client
        r = c.get('/')
        # register
        r = c.post('/register/', dict(username='test-2', password='test-2xx', password2='test-2xx', email="test-2@example.com"),  follow=True)
        assert b'login' not in r.content
        # logout
        r = c.get('/logout/')
        r = c.get('/')
        assert b'login' in r.content
        # test login
        r = c.post('/login/', dict(username='test-2', password='test-2xx',), follow=True)
        r = c.get('/')
        self.assertContains(r, 'in as test-2')
        #
        r = c.get('/devices/', follow=True)
        self.assertContains(r, 'as test-2')

    def test_basic(self):
        c = self.client
        c.get('/')
        c.get('/login/')
        r = c.post('/login/', {'username': 'test-user', 'password': 'test2'})
        #p- r.status_code
        c.login(username='test-user', password='test2')
        r = c.get('/')
        self.assertContains(r, 'test-user')
        r = c.get('/devices/')
        r = c.post('/devices/create/', dict(type='PurpleRobot', name='test-device-150'))
        #p- r.url
        #import IPython; IPython.embed()
        r = c.get('/devices/')


    def test_group(self):
        c = self.client
        r = c.post('/login/', dict(username='test-user', password='test2'))
        r = c.get('/group/')
        r = c.post('/group/', dict(invite_code='groupinvite'))
        self.assertContains(r, 'Test Group')
        r = c.post('/group/', dict(invite_code='groupinvite', groups='Test Group'))
        models.GroupSubject.objects.filter(user__username='test-user', group__slug='test-group')
        #import IPython ; IPython.embed()
