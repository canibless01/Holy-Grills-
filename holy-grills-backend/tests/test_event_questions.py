import pytest
from app.utils.event_questions import validate_questions, validate_answers

FIELDS=[{'name':'department','label':'Department','type':'select','options':['Computing','Agriculture'],'required':True},{'name':'interests','label':'Interests','type':'multiselect','options':['Music','Food']},{'name':'agreement','label':'Consent','type':'checkbox','required':True}]

def test_questions_round_trip_and_strip_unknown_answers():
 fields=validate_questions(FIELDS)
 assert validate_answers(fields,{'department':'Computing','interests':['Food'],'agreement':True,'organizer_amount':999})=={'department':'Computing','interests':['Food'],'agreement':True}

@pytest.mark.parametrize('answer',[{}, {'department':'Engineering','agreement':True},{'department':'Computing','agreement':False},{'department':'Computing','agreement':True,'interests':['Other']},{'department':'Computing','agreement':True,'interests':['Food','Food']}])
def test_required_and_choice_answers_are_enforced_server_side(answer):
 with pytest.raises(ValueError):validate_answers(FIELDS,answer)

@pytest.mark.parametrize('field', [{'name':'bad key','label':'L'}, {'name':'x','label':'L','type':'radio','options':[]}, {'name':'x','label':'L','type':'select','options':['A','A']}, {'name':'x','label':'L','type':'text','required':'false'}, {'name':'x','label':'L','type':'html'}])
def test_bad_question_definitions_fail_closed(field):
 with pytest.raises(ValueError):validate_questions([field])

@pytest.mark.parametrize('kind,value',[('number','NaN'),('date','not-date'),('email','not-email')])
def test_typed_answers(kind,value):
 with pytest.raises(ValueError):validate_answers([{'name':'x','type':kind}],{'x':value})
