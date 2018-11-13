from functools import partial
import os
import sys
import yaml

from django import forms



# django.forms field/widget types.  These are used to override the
# HTML in the form and add in section headings, or special input
# types like a time picker
class TimeInput(forms.TimeInput):
    """HTML5 time input."""
    input_type = 'time'
class SliderInput(forms.NumberInput):
    """HTML5 slider input widget.

    Sets a reasonable max width and range from 0 to 100."""
    input_type = 'range'
    attrs = dict(min=0, max=100, style="max-width: 400px")
    def __init__(self, *args, **kwargs):
        attrs = dict(self.attrs)
        attrs.update(kwargs.get('attrs', {}))
        super(SliderInput, self).__init__(*args, attrs=attrs, **kwargs)
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
class SliderField(forms.IntegerField):
    widget = SliderInput




# These define different field types for the survey.  We can add more
# if needed, for example a Choice field with default options, or other
# fancy types of inputs.
class _SurveyField(object):
    not_a_question = False   # for marking instructions/section headings
    widget = None
    required = None
    def __init__(self, question):
        self.question = question
class Bool(_SurveyField):
    required = False
    field = forms.BooleanField
class Char(_SurveyField):   # alias: Text
    field = forms.CharField
Text = Char
class BaseChoice(_SurveyField):
    # Only for overriding
    def __init__(self, question):
        self.question = question
class Choice(BaseChoice):   # alias: Radio
    def __init__(self, question, choices):
        self.question = question
        self.choices = choices
Radio = Choice
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
class Section(_SurveyField):
    not_a_question = True
    field = SectionField
class Instructions(_SurveyField):
    not_a_question = True
    field = InstructionsField
class Slider(_SurveyField):
    """A slider with range 0 to 100."""
    field = SliderField
Scale = Slider

type_map = {
    'text': Char, 'char': Char,
    'radio': Choice, 'choice': Choice,
    'numeric': Float, 'float': Float,
    'integer': Integer,
    'time': Time,
    'scale': Slider, 'slider': Slider,
    'bool': Bool,
    'instructions': Instructions,
    'section': Section,
    }

def convert_questions(data, survey_id=None):
    """Convert just a list of questions to the class objects.

    Input: [ question, ...]

    Output: [ question list containing Python classes which is usable by
    Koota surveys
    """
    qlist = [ ]
    for row in data:
        # Auto-generate ID or take the row ID
        if 'id' not in row:
            if schedule_id is None:
                raise ValueError('Survey yaml question or survey needs an "id" value: {}'.format(row))
            row['id'] = survey_id['id'] + '_{:03d}'.format(i)
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
                raise ValueError("Survey yaml question %s has no type specified: If you don't specify title, you must have exactly one key that matches one of the field types."%id_)
            type_ = possible_types.pop()
            title = row.get('title', row.get(type_))
        # Process all of our posibilities.
        if type_.lower() in {'radio', 'choice', 'quickanswer'}:
            choices = row['answers']
            qlist.append((id_, Choice(title, choices)))
        # All the rest should be auto-generated:
        elif type_.lower() in type_map:
            qlist.append((id_, type_map[type_.lower()](title)))
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
    survey_data['questions'] = convert_questions(data['questions'])
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

