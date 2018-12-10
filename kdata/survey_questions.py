from functools import partial
import os
import sys
import yaml

from django import forms
from django.forms import widgets
from django.utils.safestring import mark_safe



# django.forms field/widget types.  These are used to override the
# HTML in the form and add in section headings, or special input
# types like a time picker
class TimeInput(forms.TimeInput):
    """HTML5 time input."""
    input_type = 'time'
class DateInput(forms.DateInput):
    """HTML5 date input."""
    input_type = 'date'  #datetime-local -> has no timezone picker
def SliderInputFactory(**userattrs):
    class SliderInput(forms.NumberInput):
        """HTML5 slider input widget.

        Sets a reasonable max width and range from 0 to 100."""
        input_type = 'range'
        attrs = dict(min=0, max=100, style="max-width: 400px")
        attrs.update(userattrs)
        def __init__(self, *args, required=None, **kwargs):
            attrs = dict(self.attrs)
            attrs.update(kwargs.pop('attrs', {}))
            super(SliderInput, self).__init__(*args, attrs=attrs, **kwargs)
    return SliderInput
SliderInput = SliderInputFactory()
class InstructionsWidget(forms.Widget):
    """Fake widget that returns nothing.

    This widget is not for an actual input, but is just used for text
    which has no value associated with it.
    """
    def render(self, name, value, attrs=None, **kwargs):
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
def SliderFieldFactory(**userattrs):
    class SliderField(forms.IntegerField):
        widget = SliderInputFactory(**userattrs)
    return SliderField
SliderField = SliderFieldFactory()
#class CheckboxChoiceField(forms.Field):
#    widget = widgets.CheckboxSelectMultiple


# These define different field types for the survey.  We can add more
# if needed, for example a Choice field with default options, or other
# fancy types of inputs.
class _SurveyField(object):
    not_a_question = False   # for marking instructions/section headings
    widget = None
    required = None
    allow_required = True
    #field = xxxField  # implemented in subclasses
    def __init__(self, question, required=None):
        self.question = question
        self.required = required
class Bool(_SurveyField):
    allow_required = False
    field = forms.BooleanField
class Char(_SurveyField):   # alias: Text
    field = forms.CharField
Text = Char
class BaseChoice(_SurveyField):
    # Only for overriding
    def __init__(self, question, required=None):
        self.question = question
        self.required = required
class Choice(BaseChoice):   # alias: Radio
    def __init__(self, question, choices, required=None):
        self.question = question
        self.choices = choices
        self.required = required
class Checkboxes(Choice):
    field = forms.MultipleChoiceField
    widget = widgets.CheckboxSelectMultiple
class Float(_SurveyField):  # alias: numeric
    field = forms.FloatField
Numeric = Float
class Integer(_SurveyField):
    field = forms.IntegerField
class Time(_SurveyField):
    field = partial(forms.TimeField, input_formats=[
        '%H:%M:%S', '%H:%M', '%H.%M', '%H,%M','%H %M', '%H%M', ])
    widget = TimeInput
#    widget = admin_widgets.AdminTimeWidget
class Date(_SurveyField):
    field = partial(forms.DateField, input_formats=[
        '%Y-%m-%d', '%d.$m.$Y'])
    widget = DateInput
class Section(_SurveyField):
    allow_required = False
    not_a_question = True
    field = SectionField
class Instructions(_SurveyField):
    allow_required = False
    not_a_question = True
    field = InstructionsField
# These are immediately initialized in this file
class Slider(_SurveyField):
    """A slider with range 0 to 100.

    Valid attrs are 'min', 'max', and 'step'."""
    def __init__(self, question, **attrs):
        super().__init__(question)
        self.field = SliderFieldFactory(**attrs)
Scale = Slider
class LikertSlider(Slider):
    def __init__(self, question, max=5, step=1, max_label='', min_label='', required=None):
        if max_label or min_label:
            question = question + " (%s←→%s)"%(min_label, max_label)
        super().__init__(question, required=required)
        self.field = SliderFieldFactory(min=1, max=max, step=step)
class LikertChoice(Choice):
    def __init__(self, question, max=5, step=1, max_label='', min_label='', required=None):
        choices = ["★" * i for i in range(1, max+1)]
        if min_label:
            # The space is two unicode EM SPACEs
            choices[0] = choices[0] + '  ' + min_label
        if max_label:
            choices[-1] = choices[-1] + '  ' + max_label
        super().__init__(question, choices, required=required)
Likert = LikertChoice



type_map = {
    'text': Char, 'char': Char,
    'radio': Choice, 'choice': Choice, 'quickanswer': Choice,
    'numeric': Float, 'float': Float,
    'integer': Integer,
    'time': Time,
    'date': Date,
    'scale': Slider, 'slider': Slider,
    'bool': Bool, 'check': Bool,
    'instructions': Instructions,
    'section': Section,
    'likert':Likert, 'likertslider':LikertSlider, 'likertchoice':LikertChoice,
    'checkboxes': Checkboxes,
    }

def convert_questions(data, survey_id=None):
    """Convert just a list of questions to the class objects.

    Input: [ question, ...]

    Output: [ question list containing Python classes which is usable by
    Koota surveys
    """
    qlist = [ ]
    for i, row in enumerate(data):
        # Auto-generate ID or take the row ID
        if 'id' not in row:
            if survey_id is None:
                raise ValueError('An ID value must be defined in either the survey or the question: {}'.format(row))
            id_ = survey_id + '_{:03d}'.format(i)
        else:
            id_ = row['id']
        # Determine the type.  Either explicit 'type: xxx' or implicit
        # '<type>: <title>'
        if 'type' in row:
            type_ = row['type']
            title = row.get('title', row.get('instructions'))
        else:
            possible_types = set(row) & set(type_map)
            if len(possible_types) != 1:
                raise ValueError("Survey yaml question %s has no type specified: If you don't specify title, you must have exactly one key that matches one of the field types (%s)."%(id_, row))
            type_ = possible_types.pop()
            title = row.get('title', row.get(type_))
        required = row.get('required')
        # Process all of our posibilities.
        if type_.lower() in {'radio', 'choice', 'quickanswer', 'checkboxes'}:
            choices = row['answers']
            qlist.append((id_, type_map[type_.lower()](title, choices, required=required)))
        elif type_.lower() in {'slider', 'likert', 'likertslider'}:
            attrs = { }
            for attrname in ['min', 'max', 'step', 'max_label', 'min_label']:
                if attrname in row: attrs[attrname] = row[attrname]
            qlist.append((id_, type_map[type_.lower()](title, required=required, **attrs)))
        # All the rest should be auto-generated:
        elif type_.lower() in type_map:
            qlist.append((id_, type_map[type_.lower()](title, required=required)))
        # TODO: add likert?
        else:
            raise ValueError("Unknown question type: ...")
    return qlist

def convert(data):
    """Covert YAML file into full structure for Koota surveys.

    Input: a loaded YAML(or json) file.  See
    kdata/examples/survey_question.syaml for an example.

    Output: A dict struct like {name="Title", questions=[list of
    questions]}.
    """
    survey_data = { }
    if 'title' in survey_data:
        survey_data['name'] = data['title']
    survey_data['questions'] = convert_questions(data['questions'],
                                                 survey_id=data.get('id'))
    survey_data['require_all'] = data.get('require_all', False)
    return survey_data



sample_data = open(os.path.join(os.path.dirname(__file__), 'examples/survey_questions.yaml')).read()

# Test either the sample data or files on cammand line.
if __name__ == "__main__":
    if len(sys.argv) == 1:
        # Print sample data
        print(yaml.dump(convert(yaml.load(sample_data))))
    else:
        # Load all data
        for arg in sys.argv[1:]:
            for doc in yaml.load_all(open(arg)):
                print(yaml.dump(convert(doc)))

