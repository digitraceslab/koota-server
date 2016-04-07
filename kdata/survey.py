import base64
from calendar import timegm
import datetime
from functools import partial
import json
from json import loads, dumps
import os
import six

from django import forms
from django.conf import settings
from django.contrib.admin import widgets as admin_widgets
from django.core.urlresolvers import reverse, reverse_lazy
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect, Http404
from django.views.generic import ListView, DetailView, CreateView, UpdateView, FormView
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.utils.translation import ugettext_lazy as _
from django.template.response import TemplateResponse

#import floppyforms as forms

from . import converter
from . import models
from . import devices
from . import util
from . import views

# django.forms field/widget types.  These are used to override the
# HTML in the form and add in section headings, or special input
# types like a time picker
class TimeInput(forms.TimeInput):
    """HTML5 time input."""
    input_type = 'time'
class InstructionsWidget(forms.Widget):
    """Fake widget that returns nothing.

    This widget is not for an actual input, but is just used for text
    which has no value associated with it.
    """
    def render(self, name, value, attrs=None):
        return ''
class InstructionsField(forms.Field):
    """Field for a text paragraph"""
    widget = InstructionsWidget
    css_class = 'instructions'
    def __init__(self, label, **kwargs):
        super(InstructionsField, self).__init__(label_suffix='', **kwargs)
        self.label = mark_safe('<span class="{css_class}">{0}</span>'.format(label, css_class=self.css_class))
class SectionField(InstructionsField):
    """Field for a section heading."""
    css_class = 'section-heading'

# These define different field types for the survey.  We can add more
# if needed, for example a Choice field with default options, or other
# fancy types of inputs.
class _SurveyField(object):
    not_a_question = False   # for marking instructions/section headings
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
    field = partial(forms.TimeField, input_formats=[
        '%H:%M:%S', '%H:%M', '%H.%M', '%H,%M','%H %M', '%H%M', ])
    widget = TimeInput
#    widget = admin_widgets.AdminTimeWidget
class Section(_SurveyField):
    not_a_question = True
    field = SectionField
class Instructions(_SurveyField):
    not_a_question = True
    field = InstructionsField

# A JSON encoder that can convert date and time objects to strings.
def field_to_json(x):
    if isinstance(x, _SurveyField):
        return (x.__class__.__name__,
                x.__dict__)
    if isinstance(x, datetime.time):
        return x.strftime('%H:%M:%S')
    if isinstance(x, datetime.datetime):
        return timegm(x.utctimetuple())
    if isinstance(x, datetime.date):
        return x.strftime('%Y-%m-%d')
    raise ValueError("JSON enocde error: unknown type: %r"%x)
json_encode = json.JSONEncoder(default=field_to_json).encode

# Helper to make a form out of the fields.
def make_form(survey_data):
    """Take Python data and return a django.forms.Form."""
    form_fields = { }
    question_order = [ ]
    for i, (tag, row) in enumerate(survey_data):
        if isinstance(row, Choice):
            form_fields[tag] = forms.ChoiceField(
                [(i,x) for i,x in enumerate(row.choices)],
                label=row.question,
                widget=forms.RadioSelect,
                required=False)
        else:
            form_fields[tag] = row.field(label=row.question, required=False,
                                         widget=row.widget)
        form_fields[tag].not_a_question = row.not_a_question
        if not row.not_a_question:
            question_order.append(tag)
    # The _question_order field allows us to convey the order of
    # questions to the next stage.  It is important because it is
    # possible for order to be randomized, and each form generation
    # would have a different order!  TODO: what about multiple
    # submissions?
    form_fields['_question_order'] = forms.CharField(
                                         required=False,
                                         initial=','.join(question_order),
                                         widget=forms.HiddenInput)
    form_fields['_question_order'].not_a_question = True
    Form = type('DynamicSurveyForm',
                (forms.Form, ),
                form_fields)
    return Form


def take_survey(request, token):
    """This is the view which handles surveys."""
    context = c = { }
    # Find the survey data via token, then find the
    try:
        token_row = models.SurveyToken.objects.get(token=token)
    except models.SurveyToken.DoesNotExist:
        return HttpResponse('Survey %s does not exist...'%token,
                            status=404)
    device = models.SurveyDevice.get_by_id(token_row.device_id)
    survey_class = device.get_class()

    survey_data = survey_class.get_survey(data=token_row.data, device=device)

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
            data['survey_name'] = survey_data.get('name', survey_class.__name__)
            data['token'] = token
            data['answers'] = { }
            # Make a 'question order' lookup to get question order of
            # the last round.
            question_order = form.cleaned_data.pop('_question_order', '').split(',')
            question_order = { tag:i for i,tag in enumerate(question_order) }
            # Go through and record all answers.
            for tag, field in form.fields.items():
                if getattr(field, 'not_a_question', False): continue
                q = field.label
                a = form.cleaned_data[tag]
                order = question_order.get(tag)
                data['answers'][tag] = dict(q=q, a=a, order=order)

            # Save the data
            data['access_time'] = token_row.ts_access
            data['submit_time'] = token_row.ts_submit
            #import pprint ; pprint.pprint(data)
            data = json_encode(data)
            views.save_data(data=data, device_id=token_row.device_id,
                            request=request)
            c['success'] = True
        else:
            pass
    else:
        token_row.ts_access = timezone.now()
        form = c['form'] = Form()
    token_row.save()
    return TemplateResponse(request, 'koota/survey.html', context)




# The two converters
class SurveyAnswers(converter._Converter):
    header = ['id', 'access_time', 'submit_time', 'question', 'answer', 'order']
    desc = "Survey questions and answers"
    def convert(self, rows, time=lambda x:x):
        for ts, data in rows:
            data = loads(data)
            for slug, x in data['answers'].items():
                yield (slug,
                       time(data['access_time']),
                       time(data['submit_time']),
                       x['q'],
                       x['a'],
                       x.get('order',''),)
class SurveyMeta(converter._Converter):
    header = ['name', 'access_time', 'submit_time', 'seconds', 'n_questions']
    desc = "Survey questions and answers"
    def convert(self, rows, time=lambda x:x):
        for ts, data in rows:
            data = loads(data)
            yield (data.get('survey_name', None),
                   data['access_time'],
                   data['submit_time'],
                   data['submit_time']-data['access_time'],
                   len(data['answers']),
                   )



# Below we have the survey devices.  These are auto-registering
# subclasses of devices._Device.
class _SurveyMetaclass(type):
    """Automatically register new devices

    This metaclass will call devices.register_device automatically
    upon class creation.
    """
    def __new__(mcs, name, bases, dict):
        cls = type.__new__(mcs, name, bases, dict)
        if (cls.__name__ != 'BaseSurvey'
            and not cls.__name__.startswith('_')
            and dict.get('_register_device', True)
           ):
            devices.register_device(cls, getattr(cls, 'desc', None))
        return cls

from . import converter
@six.add_metaclass(_SurveyMetaclass)
class BaseSurvey(devices._Device):
    dbmodel = models.SurveyDevice
    converters = [converter.Raw,
                  SurveyAnswers,
                  SurveyMeta,
                 ]

    @classmethod
    def get_survey(cls, data, device):
        """This method should be overwritten to return the survey data."""
        raise NotImplementedError("This survey is not yet configured, "
                                  "define get_survey().")

    @classmethod
    def create_hook(cls, instance, user):
        """In this create hook, do survey specifc setup.

        This is run every time a new device is created.  Mainly, this
        is used for making the survey tokens and for ephemeral
        surveys, any setup needed there.
        """
        super(BaseSurvey, cls).create_hook(instance, user)
        device_id = instance.device_id

        # Set any tokens we need
        token = base64.b16encode(os.urandom(5))
        surveytoken_row = models.SurveyToken(token=token, device_id=device_id, user=instance.user)
        instance.token = token
        surveytoken_row.device = instance

        # Don't forget to save.
        instance.save()
        surveytoken_row.save()

    instructions = (
        """You should program the URL """
        """<b><tt><a href="https://{main_domain}{post}">https://{main_domain}{post}</a></tt></b> """
        """take this survey.""")
    @classmethod
    def configure(cls, device):
        """Information for the device configure page."""
        instructions = cls.instructions.format(
            post=reverse_lazy('survey-take', kwargs=dict(token=device.surveydevice.token)),
            post_domain=settings.POST_DOMAIN,
            main_domain=settings.MAIN_DOMAIN,
            token=device.surveydevice.token,
            )
        return dict(qr=False,
                    raw_instructions=instructions)



class TestSurvey1(BaseSurvey):
    """This is a test survey."""
    @classmethod
    def get_survey(cls, data, device):
        questions = [
            ('header1',       Section('Section 1')),
            ('header2',       Instructions('This is a section heading')),
            ('sleep-quality', Choice('How did you sleep?', (1, 2, 3, 4, 5))),
            ('fine',          Bool('Are you fine?')),
            ('asleep',        Time('When did you go to sleep?')),
            ('woke-up',       Time('When did you wake up?')),
            ('header3',       Section('Section 2')),
            ('fine3',         Bool('Are you fine?')),
            ('fine4',         Bool('Are you fine?')),
            ('fine5',         Bool('Are you fine?')),
            ('drinks',        Integer('How many drinks did you have?')),
        ]
        # Can do extra logic here
        survey_data = {'name': 'Test Survey 1',
                       'id': 1,
                       'questions':questions,
                   }

        return survey_data
#devices.register_device(TestSurvey1, "Test Survey #1")
