import json
import os
import base64

from django import forms
from django.conf import settings
from django.core.urlresolvers import reverse, reverse_lazy
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect, Http404
from django.views.generic import ListView, DetailView, CreateView, UpdateView, FormView
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _
from django.template.response import TemplateResponse

from . import models
from . import devices
from . import util
from . import views


class _SurveyField(object):
    widget = None
    def __init__(self, question):
        self.question = question
class Bool(_SurveyField):
    field = forms.BooleanField
class Char(_SurveyField):
    field = forms.CharField
class Choice(_SurveyField):
    def __init__(self, question, choices):
        self.question = question
        self.choices = choices
class Integer(_SurveyField):
    field = forms.IntegerField
class Time(_SurveyField):
    field = forms.TimeField

def field_to_json(x):
    if isinstance(x, _SurveyField):
        return (x.__class__.__name__,
                x.__dict__)
    raise ValueError("JSON enocde error: unknown type: %r"%x)
json_encode = json.JSONEncoder(default=field_to_json).encode


survey_data = {'name': 'Survey 1',
               'id': 1,
               'fields': [
                   ('sleep-quality', Choice('How did you sleep?', (1, 2, 3, 4, 5))),
                   ('fine',          Bool('Are you fine?')),
                   ]
           }


def make_form(data):
    """Take Python data and return a django.forms.Form."""
    form_fields = { }
    for i, (tag, row) in enumerate(data):
        if isinstance(row, Choice):
            form_fields[tag] = forms.ChoiceField(
                [(i,x) for i,x in enumerate(row.choices)],
                label=row.question,
                widget=forms.RadioSelect,
                required=False)
        else:
            form_fields[tag] = row.field(label=row.question, required=False,
                                         widget=row.widget)

    Form = type('DynamicSurveyForm',
                (forms.Form, ),
                form_fields)
    return Form


def take_survey(request, token):
    """This is the view which handles surveys."""
    context = c = { }
    # Find the survey data via token, then find the
    token_row = models.SurveyToken.objects.get(token=token)
    device = models.SurveyDevice.get_by_id(token_row.device_id)
    survey_class = device.get_class()

    survey_data = survey_class.get_survey(data=token_row.data)

    Form = make_form(survey_data['questions'])
    survey_name = c['survey_name'] = survey_data.get('name', survey_class.__name__)

    if request.method == 'POST':
        form = c['form'] = Form(request.POST)
        if form.is_valid():
            token_row.ts_submit = timezone.now()
            # make the json
            #import IPython ; IPython.embed()
            data = { }
            data['survey_data'] = dict(survey_data)
            data['token'] = token
            data['answers'] = { }
            # Go through and record all answers.
            for tag, field in form.fields.items():
                q = field.label
                a = form.cleaned_data[tag]
                data['answers'][tag] = dict(q=q, a=a)

            # Save the data
            data = json_encode(data)
            views.save_data(data=data, device_id=token_row.device_id,
                            request=request)
            #print(data)
            c['success'] = True
        else:
            pass
    else:
        token_row.ts_access = timezone.now()
        form = c['form'] = Form()
    token_row.save()
    return TemplateResponse(request, 'koota/survey.html', context)


from . import converter
class _Survey(devices._Device):
    dbmodel = models.SurveyDevice
    converters = [converter.Raw,
                 ]

    @classmethod
    def get_survey(cls, data):
        """This method should be overwritten to return the survey data."""
        raise NotImplementedError("This is an ABC.")

    @classmethod
    def create_hook(cls, instance, user):
        """In this create hook, do survey specifc setup.

        Mainly, this is used for making the survey tokens and for
        ephemeral surveys, any setup needed there.
        """
        super(_Survey, cls).create_hook(instance, user)
        device_id = instance.device_id

        # Set any tokens we need
        token = base64.b16encode(os.urandom(5))
        surveytoken_row = models.SurveyToken(token=token, device_id=device_id, user=instance.user)
        instance.token = token
        surveytoken_row.device = instance

        # Don't forget to save.
        instance.save()
        surveytoken_row.save()

    @classmethod
    def configure(cls, device):
        instructions = """You should program the URL <tt>https://{main_domain}{post}</tt> to
        take this survey.  """.format(
            post=reverse_lazy('survey-take', kwargs=dict(token=device.surveydevice.token)),
            post_domain=settings.POST_DOMAIN,
            main_domain=settings.MAIN_DOMAIN,
            )
        return dict(qr=False,
                    raw_instructions=instructions)



class TestSurvey1(_Survey):
    """This is a test survey."""
    @classmethod
    def get_survey(cls, data):
        questions = [
            ('sleep-quality', Choice('How did you sleep?', (1, 2, 3, 4, 5))),
            ('fine',          Bool('Are you fine?')),
            ('asleep',        Time('When did you go to sleep?')),
            ('woke-up',       Time('When did you wake up?')),
            ('fine3',         Bool('Are you fine?')),
            ('fine4',         Bool('Are you fine?')),
            ('fine5',         Bool('Are you fine?')),
        ]
        # Can do extra logic here
        survey_data = {'name': 'Test Survey 1',
                       'id': 1,
                       'questions':questions,
                   }

        return survey_data
devices.register_device(TestSurvey1, "Test Survey #1")
