/** Inert rich-text preview, using the same tag/style limits as the send contract. */
export function safeBlastUrl(value:string):string|undefined {
  if(typeof value!=='string'||!value||value.length>2048)return undefined;
  try {
    const decoded=decodeURIComponent(decodeURIComponent(value));
    if(/[\s\\\x00-\x1f]/.test(decoded))return undefined;
    if(decoded.startsWith('/')&&!decoded.startsWith('//'))return value;
    const url=new URL(decoded);
    return url.protocol==='https:'&&!url.username&&!url.password&&(!url.port||url.port==='443')?value:undefined;
  }catch{return undefined;}
}
export function safeBlastHtml(value:string):string {
  if(typeof DOMParser==='undefined')return '';
  const document=new DOMParser().parseFromString(value,'text/html');
  const output=document.createElement('div');
  const allowed=new Set(['p','div','span','strong','b','em','i','u','s','strike','ol','ul','li','h1','h2','h3','h4','br','blockquote','a']);
  const blocked=new Set(['script','style','iframe','object','svg','math','template']);
  const copy=(source:Node,parent:Node)=>{
    if(source.nodeType===3){parent.appendChild(document.createTextNode(source.textContent||''));return;}
    if(source.nodeType!==1)return;
    const element=source as Element;const tag=element.tagName.toLowerCase();
    if(blocked.has(tag))return;
    const target=allowed.has(tag)?document.createElement(tag):parent;
    if(target!==parent){
      const href=tag==='a'?safeBlastUrl(element.getAttribute('href')||''):undefined;
      if(href)(target as Element).setAttribute('href',href);
      const styles=(element.getAttribute('style')||'').split(';').filter(rule=>/^\s*(?:text-align\s*:\s*(?:left|center|right)|(?:color|background-color)\s*:\s*#[0-9a-f]{3}(?:[0-9a-f]{3})?)\s*$/i.test(rule));
      if(styles.length)(target as Element).setAttribute('style',styles.join(';'));
      parent.appendChild(target);
    }
    Array.from(source.childNodes).forEach(child=>copy(child,target));
  };
  Array.from(document.body.childNodes).forEach(child=>copy(child,output));
  return output.innerHTML;
}
export const plainBlastHtml=(value:string)=>value.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\n/g,'<br>');
