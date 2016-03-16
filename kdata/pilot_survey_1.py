from kdata.survey import BaseSurvey, Bool, Char, Choice, Integer, Time

class PilotSurvey1(BaseSurvey):
    """This is pilot survey 1."""
    @classmethod
    def get_survey(cls, data):
        questions = [
            ('interest', Choice('Little interest or pleasure in doing things', 
            	("Not at all", "Several times", "More than half of the time", "Nearly all the time"))),
            ('depressed', Choice('Feeling down, depressed, or hopeless', 
            	("Not at all", "Several times", "More than half of the time", "Nearly all the time"))),
            ('tired', Choice('Feeling tired or having little energy',
            	("Not at all", "Several times", "More than half of the time", "Nearly all the time"))),
            ('failure', Choice('Feeling bad about yourself — or that you are a failure or have let yourself or your family down', 
            	("Not at all", "Several times", "More than half of the time", "Nearly all the time"))),
            ('nervous', Choice('Feeling nervous, anxious or on edge',
            	("Not at all", "Several times", "More than half of the time", "Nearly all the time"))),
            ('worrying', Choice('Not being able to stop or control worrying',
            	("Not at all", "Several times", "More than half of the time", "Nearly all the time"))),
            ('relaxing', Choice('Trouble relaxing',
            	("Not at all", "Several times", "More than half of the time", "Nearly all the time"))),
            ('annoyed', Choice('Becoming easily annoyed or irritable', 
            	("Not at all", "Several times", "More than half of the time", "Nearly all the time")))
        ]
        # Can do extra logic here
        survey_data = {'name': 'Pilot Survey 1',
                       'id': 1,
                       'questions':questions,
                   }

        return survey_data
