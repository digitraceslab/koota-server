from kdata.survey import BaseSurvey, Bool, Char, Choice, Integer, Time

class PilotSurvey2(BaseSurvey):
    """This is pilot survey 2."""
    @classmethod
    def get_survey(cls, data):
        questions = [
            ('organized', Choice('Difficulty getting things in order when you have to do a task that requires organization?',
            	("Never", "Almost Never", "Sometimes", "Fairly Often", "Very Often"))),
            ('remembering', Choice('Have problems remembering appointments or obligations?',
            	("Never", "Almost Never", "Sometimes", "Fairly Often", "Very Often"))),
            ('delay_in_starting', Choice('Avoid or delay getting started when you have a task that requires a lot of thought?',
            	("Never", "Almost Never", "Sometimes", "Fairly Often", "Very Often"))),
            ('reading', Choice('Read something and find you haven\'t been thinking about it and must read it again?',
            	("Never", "Almost Never", "Sometimes", "Fairly Often", "Very Often"))),
            ('turning_off', Choice('Find you forget whether you\'ve turned off a light or a fire or locked the door?',
            	("Never", "Almost Never", "Sometimes", "Fairly Often", "Very Often"))),
            ('hearing', Choice('Fail to hear people speaking to you when you are doing something else?',
            	("Never", "Almost Never", "Sometimes", "Fairly Often", "Very Often"))),
            ('deciding', Choice('Have trouble making up your mind?',
            	("Never", "Almost Never", "Sometimes", "Fairly Often", "Very Often"))),
            ('daydream', Choice('Daydream when you ought to be listening to something?',
            	("Never", "Almost Never", "Sometimes", "Fairly Often", "Very Often"))),
            ('distract', Choice('Start doing one thing at home and get distracted into doing something else unintentionally?', 
            	("Never", "Almost Never", "Sometimes", "Fairly Often", "Very Often"))),
            ('unexpected', Choice('Start doing one thing at home and get distracted into doing something else unintentionally?',
            	("Never", "Almost Never", "Sometimes", "Fairly Often", "Very Often"))),
            ('control', Choice('Feel that you were unable to control the important things in your life?',
            	("Never", "Almost Never", "Sometimes", "Fairly Often", "Very Often"))),
            ('stressed', Choice('Feel nervous and “stressed”?',
            	("Never", "Almost Never", "Sometimes", "Fairly Often", "Very Often"))),
            ('irritations', Choice('Be able to control irritations in your life?',
            	("Never", "Almost Never", "Sometimes", "Fairly Often", "Very Often")))
        ]
        # Can do extra logic here
        survey_data = {'name': 'Pilot Survey 2',
                       'id': 2,
                       'questions':questions,
                   }

        return survey_data
