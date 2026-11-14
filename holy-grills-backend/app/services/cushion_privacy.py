"""Public projections keep internal delivery allocations out of customer data.

Explicit existing columns also let RLS-scoped queries keep working when database
column grants hide the new internal amounts. Service-role accounting reads do
not use these projections.
"""
import re

PUBLIC_COLUMNS = {
    'menu_items': 'id,category_id,name,slug,description,image_url,price,hp_earn,is_available,is_featured,tags,options,created_at,updated_at,deleted_at,daily_limit,hp_earn_value,hp_multiplier,campus_id,is_secret',
    'menu_addons': 'id,name,description,price,is_available,is_archived,sort_order,created_at,updated_at,group_id,campus_id',
    'menu_item_variation_options': 'id,variation_group_id,name,price_delta,is_available,sort_order,created_at,campus_id,is_archived',
    'order_items': 'id,order_id,menu_item_id,name_snapshot,price_snapshot,hp_earn_snapshot,quantity,options_snapshot,line_total,created_at,selected_variations,is_addon,addon_id,hp_multiplier_snapshot,campus_id,squad_member_email',
    'order_addon_selections': 'id,order_item_id,addon_id,group_id,name_snapshot,price_delta_snapshot,quantity,created_at,campus_id',
}


def public_projection(table, selection):
    """Expand stars, including nested PostgREST relations, retaining aliases."""
    parts=[];start=depth=0
    for i,char in enumerate(selection):
        if char=='(': depth+=1
        elif char==')': depth-=1
        elif char==',' and depth==0: parts.append(selection[start:i]);start=i+1
    parts.append(selection[start:]);result=[]
    for raw in parts:
        part=raw.strip()
        if part=='*' and table in PUBLIC_COLUMNS:
            result.append(PUBLIC_COLUMNS[table])
        elif '(' in part and part.endswith(')'):
            head,inner=part.split('(',1)
            match=re.fullmatch(r'(?:\w+:)?(\w+)(?:![\w]+)*',head)
            relation=match.group(1) if match else ''
            result.append(head+'('+public_projection(relation,inner[:-1])+')')
        else: result.append(part)
    return ','.join(result)


def strip_internal(value):
    if isinstance(value, dict):
        changed=False;clean={}
        for key,item in value.items():
            if key.startswith(('cushion_', '_cushion_')):
                changed=True;continue
            item,child_changed=strip_internal(item);changed|=child_changed;clean[key]=item
        return (clean,True) if changed else (value,False)
    if isinstance(value,list):
        children=[strip_internal(item) for item in value]
        return ([item for item,_ in children],True) if any(changed for _,changed in children) else (value,False)
    return value,False


def install_response_privacy(app):
    from flask import g
    @app.after_request
    def hide_customer_cushion_fields(response):
        if getattr(g,'user_role',None) in ('admin','super_admin') or not response.is_json or response.is_streamed:
            return response
        value=response.get_json(silent=True)
        cleaned,changed=strip_internal(value)
        if changed: response.set_data(app.json.dumps(cleaned))
        return response
