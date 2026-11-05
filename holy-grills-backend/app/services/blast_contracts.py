"""Validated rich blast content and audience contract shared by send/preview/test."""
import html
import re
from html.parser import HTMLParser
from urllib.parse import urlsplit, unquote
from app.utils.validators import validate_uuid
from app.utils.upload_urls import is_cms_image_url


def web_url(value, *, relative=True):
    if not isinstance(value, str) or not value or len(value) > 2048:
        return False
    decoded = unquote(unquote(value))
    if any(ch.isspace() or ord(ch) < 32 for ch in decoded) or '\\' in decoded:
        return False
    if relative and decoded.startswith('/') and not decoded.startswith('//'):
        return True
    try:
        parsed = urlsplit(decoded)
        return parsed.scheme == 'https' and bool(parsed.hostname) and not parsed.username and not parsed.password and parsed.port in (None, 443)
    except ValueError:
        return False


class SafeHTML(HTMLParser):
    allowed = {'p','div','span','strong','b','em','i','u','s','strike','ol','ul','li','h1','h2','h3','h4','br','blockquote','a'}
    blocked = {'script','style','iframe','object','svg','math','template'}
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.text, self.stack = [], [], []
        self.skip = 0
    def handle_starttag(self, tag, attrs):
        if tag in self.blocked:
            self.skip += 1
            return
        if self.skip or tag not in self.allowed:
            return
        safe = []
        for key,value in attrs:
            if tag == 'a' and key == 'href' and web_url(value):
                safe.append('href="'+html.escape(value, quote=True)+'"')
            if key == 'style' and isinstance(value,str):
                declarations=[]
                for declaration in value.split(';'):
                    name,sep,content=declaration.partition(':');name=name.strip().lower();content=content.strip().lower()
                    if sep and ((name=='text-align' and content in ('left','center','right')) or
                                (name in ('color','background-color') and re.fullmatch(r'#[0-9a-f]{3}(?:[0-9a-f]{3})?',content))):
                        declarations.append(name+':'+content)
                if declarations:safe.append('style="'+';'.join(declarations)+'"')
        self.parts.append('<'+tag+(' '+' '.join(safe) if safe else '')+'>')
        if tag!='br':self.stack.append(tag)
        else:self.text.append(' ')
    def handle_endtag(self, tag):
        if tag in self.blocked:
            self.skip=max(0,self.skip-1)
            return
        if self.skip or tag not in self.stack:return
        while self.stack:
            closing=self.stack.pop();self.parts.append('</'+closing+'>')
            if closing==tag:break
        self.text.append(' ')
    def handle_data(self, value):
        if not self.skip:
            self.parts.append(html.escape(value));self.text.append(value)
    def finish(self):
        while self.stack:self.parts.append('</'+self.stack.pop()+'>')
        return ''.join(self.parts).strip(), ' '.join(''.join(self.text).split())


def rich_fields(data):
    result = {}
    body_html=data.get('body_html','')
    if not isinstance(body_html,str) or len(body_html)>50000:raise ValueError('rich')
    parser=SafeHTML();parser.feed(body_html);clean,plain=parser.finish()
    if body_html:result['body_html']=clean
    for field, maximum in (('images',6),('cta_blocks',10)):
        rows=data.get(field,[])
        if not isinstance(rows,list) or len(rows)>maximum:raise ValueError('rich')
        cleaned=[]
        for row in rows:
            if not isinstance(row,dict):raise ValueError('rich')
            if field=='images':
                url,alt=row.get('url'),row.get('alt','')
                if not isinstance(alt,str) or len(alt)>500 or not is_cms_image_url(url):raise ValueError('image')
                saved={'url':url,'alt':alt}
                if row.get('link'):
                    if not web_url(row['link']):raise ValueError('link')
                    saved['link']=row['link']
            else:
                label,url,style=row.get('label'),row.get('url'),row.get('style','primary')
                if not isinstance(label,str) or not label.strip() or len(label)>120 or not web_url(url) or style not in ('primary','secondary'):raise ValueError('cta')
                saved={'label':label.strip(),'url':url,'style':style}
            # Keep editor identities for response-loss equality and stable edit controls.
            if 'id' in row:
                if not isinstance(row['id'],str) or len(row['id'])>120:raise ValueError('id')
                saved['id']=row['id']
            cleaned.append(saved)
        if field in data:result[field]=cleaned
    if 'push_image' in data:
        image=data['push_image']
        if not isinstance(image,str) or (image and not is_cms_image_url(image)):raise ValueError('push image')
        result['push_image']=image
    return result, plain


def validate_segment(segment):
    if not isinstance(segment,dict):raise ValueError('segment')
    choices={'role':('all','student','admin','kitchen','rider'), 'tier':('all','ember','flame','blaze','holy'),
             'hp_balance':('all','low','medium','high'), 'total_orders':('any','0','1-5','6-20','20+'),
             'event_attendance':('any','0','1-2','3+')}
    booleans={'has_pending_hp','has_graduated','has_active_order','has_referral','has_squad_order','has_reviewed','has_shared','has_cart'}
    strings={'campus','campus_id','department','faculty','level','level_department'}
    allowed=set(choices)|booleans|strings|{'last_login_days','last_order_days','user_ids'}
    if set(segment)-allowed:raise ValueError('segment')
    for key,value in segment.items():
        if key in choices and value not in choices[key]:raise ValueError('segment')
        if key in booleans and not isinstance(value,bool):raise ValueError('segment')
        if key in strings and (not isinstance(value,str) or len(value)>200):raise ValueError('segment')
        if key in ('last_login_days','last_order_days') and value!='any' and (isinstance(value,bool) or not isinstance(value,int) or not 1<=value<=3650):raise ValueError('segment')
        if key=='user_ids' and (not isinstance(value,list) or not 1<=len(value)<=100 or len(set(value))!=len(value) or any(not isinstance(uid,str) or not validate_uuid(uid) for uid in value)):raise ValueError('segment')
    return dict(segment)
