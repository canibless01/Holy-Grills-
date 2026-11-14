"""One bounded schema for organizer/admin questions and registration answers."""
import re
from datetime import date
from app.utils.validators import validate_email

TYPES = {'text', 'textarea', 'select', 'radio', 'multiselect', 'checkbox', 'date', 'email', 'number'}

def validate_questions(value):
    if not isinstance(value, list) or len(value) > 20:
        raise ValueError('questions')
    result = []; names = set()
    for item in value:
        if not isinstance(item, dict) or set(item) - {'name', 'label', 'type', 'required', 'options'}:
            raise ValueError('question')
        name = item.get('name'); label = item.get('label'); kind = item.get('type', 'text')
        if not isinstance(name, str) or not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_]{0,49}', name) or name in names:
            raise ValueError('name')
        if not isinstance(label, str) or not 1 <= len(label.strip()) <= 200 or kind not in TYPES or not isinstance(item.get('required', False), bool):
            raise ValueError('type')
        names.add(name)
        clean = {'name': name, 'label': label.strip(), 'type': kind, 'required': item.get('required', False)}
        if kind in ('select', 'radio', 'multiselect'):
            options = item.get('options')
            if not isinstance(options, list) or not 1 <= len(options) <= 30 or any(not isinstance(o, str) or not 1 <= len(o.strip()) <= 200 for o in options):
                raise ValueError('options')
            clean['options'] = [o.strip() for o in options]
            if len(set(clean['options'])) != len(options): raise ValueError('duplicate options')
        result.append(clean)
    return result

def validate_answers(fields, answers):
    if not isinstance(answers, dict): raise ValueError('answers')
    result = {}
    for field in fields:
        name=field['name']; value=answers.get(name); kind=field.get('type', 'text')
        missing=value is None or value == '' or value == [] or (kind == 'checkbox' and value is not True)
        if isinstance(value, str): value=value.strip();missing=not value
        if missing:
            if field.get('required'): raise ValueError(field.get('label') or name)
            continue
        if kind == 'checkbox':
            if not isinstance(value, bool): raise ValueError(name)
        elif kind == 'multiselect':
            if not isinstance(value, list) or len(value) > 30 or any(not isinstance(v,str) or v not in field.get('options',[]) for v in value) or len(value) != len(set(value)): raise ValueError(name)
        else:
            if not isinstance(value, str) or len(value)>5000: raise ValueError(name)
            if kind in ('radio','select') and value not in field.get('options',[]): raise ValueError(name)
            if kind == 'date':
                try: date.fromisoformat(value)
                except ValueError: raise ValueError(name)
            if kind == 'email' and not validate_email(value): raise ValueError(name)
            if kind == 'number':
                import math
                try:
                    if not math.isfinite(float(value)): raise ValueError(name)
                except (ValueError, OverflowError): raise ValueError(name)
        result[name]=value
    return result
