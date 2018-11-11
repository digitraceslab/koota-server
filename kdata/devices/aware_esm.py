"""

Aware reference: http://www.awareframework.com/esm/
"""
import copy
import json
import os
import sys
import yaml

import logging
LOG = logging.getLogger(__name__)

sample_data = open(os.path.join(os.path.dirname(__file__), '../examples/aware_questions.yaml')).read()


schedule_template = """\
package: com.aware.phone
schedule:
  action:
    class: ACTION_AWARE_QUEUE_ESM
    intent_action: ACTION_AWARE_QUEUE_ESM
    extras:
      esm: TEMPLATE_LIST_OF_ESMS
    type: broadcast
  schedule_id: TEMPLATE_ID
  trigger: TEMPLATE_TRIGGER
"""

def convert(data, schedule_id=None):
    """Full conversion of yaml data into Aware-sutitable schedule.
    """
    data = copy.deepcopy(data)  # 'data' modified in place
    # we must have an 'id' in here:
    if 'id' not in data:
        if schedule_id is None: raise ValueError("schedule must have an 'id' value")
        data['id'] = schedule_id
    # First get the flow questions.
    extra_esms = { }
    for id_, esm in data.get('extra', { }).items():
        esm['id'] = id_
        extra_esms[id_] = esm
    # Now assemble the main series of questions
    esms = [ ]
    for i, esm in enumerate(data['questions']):
        if 'id' not in esm:
            esm['id'] = data['id'] + '_{:03d}'.format(i)
        q = Question.new(esm, extra_esms=extra_esms)
        esms.append(q.json())
    # Make new ESMs delete all previous ESMs:
    if 'esm_replace_queue' not in esms[0]:
        esms[0]['esm_replace_queue'] = True
    # Produce overall schedule object
    schedule = yaml.load(schedule_template)
    schedule['schedule']['schedule_id'] = data['id']
    schedule['schedule']['action']['extras']['esm'] = [ {"esm":esm} for esm in esms ]
    schedule['schedule']['trigger'] = trigger = data['trigger']
    # Test the triggers
    unknown_trigger_keys = set(trigger) - set(('interval', 'interval_delayed',
                                               'minute', 'hour', 'timer',
                                               'weekday', 'month',
                                               'random_intervals'))
    if unknown_trigger_keys:
        raise ValueError("Unknown trigger keys: {}".format(unknown_trigger_keys))
    return schedule

def to_schedule(esms, trigger):
    pass




class Question(object):
    flow = None
    @staticmethod
    def new(data, extra_esms={}):
        if 'type' not in data:
            raise ValueError("ESM {} does not have  type".format(data))
        type_ = data.pop('type')
        # Find global named data['type'] in title case, initialize that.
        inst = globals()[type_.title()](data, extra_esms=extra_esms)
        return inst

    def __init__(self, data, extra_esms):
        self.extra = { }       # extra data to be added into final
        self.setup_hook(data)
        if 'id' not in data: raise ValueError("No ID attribute in {}".format(data))
        self.id_ = data.pop('id')
        self.title = data.pop('title', "")
        self.instructions = data.pop('instructions', "")
        self.submit = data.pop('submit', "OK")
        if 'flow' in data:
            # data['flows'] in a dictionary which has "answer": "next_id" pairs.
            esm_flows = [ ]
            for answer, next_id in data['flow'].items():
                if not self.is_valid_answer(answer):
                    raise ValueError("esm_flow for %s has flow answer %s but it is missing"%(
                        self.id_, answer))
                esm_flows.append({
                    "user_answer": answer,
                    "next_ems": {"esm":Question.new(extra_esms[next_id], extra_esms=extra_esms).json(),
                                 }})
            self.flow = esm_flows
            data.pop('flow')

        # Process extra type-specific parameters
        #for name, type_ in self.params:
        #    self.extra[name] = type_(data.pop(name))
        if data:
            raise ValueError("Remaining unprocessed data in %s: %s"%(self.id_, data))

    def is_valid_answer(self, answer):
        """Check if "answer" is a valid answer to this question.

        This is used to check if there are bugs in esm_flows.
        """
        return False
    def json(self):
        data = dict(esm_type=types[self.__class__.__name__.lower()],
                    esm_instructions=self.instructions,
                    esm_title=self.title,
                    esm_submit=self.submit,
                    esm_trigger = self.id_
                    )
        data.update(self.extra)
        if self.flow:
            data['esm_flows'] = self.flow
        return data
    def setup_hook(self, data):
        pass

types = {"text": 1,
         "radio": 2,
         "checkbox": 3,
         "likert": 4,
         "quickanswer": 5,
         "scale": 6,
         "numeric": 9,
         "web": 10,
    }
class Text(Question):
    pass
class Radio(Question):
    def setup_hook(self, data):
        self.extra['esm_radios'] = answers = [ ]
        self.extra['answer_id']  = answer_id = { }
        for i, val in enumerate(data.pop('answers')):
            if isinstance(val, list):
                # Includes a permenent ID field
                answers.append(val[1])
                answer_id[val[1]] = val[0]
            else:
                # No permanent ID field
                answers.append(val)
                answer_id[val] = i
    def is_valid_answer(self, answer):
        return answer in self.extra['answer_id'].values() or answer in self.extra['esm_radios']
class Likert(Question):
    def setup_hook(self, data):
        self.extra['esm_likert_max'] = data.pop('max', 5)
        if 'max_label' in data:
            self.extra['esm_likert_max_label'] = data.pop('max_label')
        if 'min_label' in data:
            self.extra['esm_likert_min_label'] = data.pop('min_label')
        if 'step' in data:
            self.extra['esm_likert_step'] = data.pop('step')
class Quickanswer(Radio):
    def setup_hook(self, data):
        super(Quickanswer, self).setup_hook(data)
        self.extra['esm_quick_answers'] = self.extra.pop('esm_radios')
        if 'submit' in data: raise ValueError("Quick answer ESM does not take 'submit' option.")
    def is_valid_answer(self, answer):
        return answer in self.extra['esm_quick_answers']
class Scale(Question):
    def setup_hook(self, data):
        self.extra['esm_scale_max'] = data.pop('max')
        self.extra['esm_scale_min'] = data.pop('min')
        self.extra['esm_scale_start'] = data.pop('start')
        if 'max_label' in data:
            self.extra['esm_scale_max_label'] = data.pop('max_label')
        if 'min_label' in data:
            self.extra['esm_scale_min_label'] = data.pop('min_label')
        if 'step' in data:
            self.extra['esm_scale_step'] = data.pop('step')
class Numeric(Question):
    pass
class Web(Question):
    def setup_hook(self, data):
        self.extra['esm_url'] = data.pop('url')



schedule_template_json = """\
{
    "schedule_NAME": [
        {
            "package": "com.aware.phone",
            "schedule": {
                "action": {
                    "class": "ACTION_AWARE_QUEUE_ESM",
                    "intent_action": "ACTION_AWARE_QUEUE_ESM",
                    "extras": {
                        "esm": [
                            {
                                "esm": {
                                    "esm_instructions": "How many stars do you feel like answering?",
                                    "esm_replace_queue": true,
                                    "esm_submit": "Submit",
                                    "esm_title": "Test of ESM star scale",
                                    "esm_type": 4
                                }
                            }
                        ]
                    },
                    "type": "broadcast"
                },
                "schedule_id": "ask_stars",
                "trigger": {
                    "hour": [
                        10,
                        12,
                        14,
                        16,
                        18,
                        20,
                        22
                    ]
                }
            }
        },
        {
            "package": "com.aware.phone",
            "schedule": {
                "action": {
                    "class": "ACTION_AWARE_QUEUE_ESM",
                    "intent_action": "ACTION_AWARE_QUEUE_ESM",
                    "extras": {
                        "esm": [
                            {
                                "esm": {
                                    "esm_instructions": "How many stars do you want to answer?",
                                    "esm_likert_max": 6,
                                    "esm_replace_queue": true,
                                    "esm_submit": "Submit",
                                    "esm_title": "Test of ESM star scale",
                                    "esm_type": 4
                                }
                            },
                            {
                                "esm": {
                                    "esm_instructions": "answer yes or no randomly.",
                                    "esm_radios": [
                                        "yes",
                                        "no"
                                    ],
                                    "esm_submit": "OK",
                                    "esm_title": "Yes or no?",
                                    "esm_type": 2
                                }
                            }
                        ]
                    },
                    "type": "broadcast"
                },
                "schedule_id": "ask_random",
                "trigger": {
                    "random_intervals": {
                        "N": 24,
                        "end": [
                            22,
                            0
                        ],
                        "min": 15,
                        "start": [
                            10,
                            0
                        ]
                    }
                }
            }
        }
    ]
}
"""



if __name__ == "__main__":
    if len(sys.argv) == 1:
        # Print sample data
        print(yaml.dump(convert(yaml.load(sample_data))))
    else:
        # Load all data
        for arg in sys.argv[1:]:
            for doc in yaml.load_all(open(arg)):
                print(yaml.dump(convert(doc)))

