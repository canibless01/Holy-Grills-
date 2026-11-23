/** Only explicitly selected public fields cross into rendered HTML/RSC payloads. */
export type Campus = {id: string; name: string; slug: string; isDefault: boolean};
export type Category = {id: string; name: string; slug: string};
export type Meal = {id: string; name: string; description: string; price: number; image: string; categoryId: string; available: boolean};
export type Hero = {title: string; subtitle: string; eyebrow: string; image: string; mobileImage: string; cta: string; destination: string};
type Row = Record<string, unknown>;
export function row(value: unknown): Row {return value && typeof value === 'object' && !Array.isArray(value) ? value as Row : {};}
export const string = (value: unknown) => typeof value === 'string' ? value : '';
export function rows(value: unknown): Row[] {return Array.isArray(value) ? value.map(row) : [];}
export function safeImage(value: unknown): string {
  try {const url = new URL(string(value));return url.protocol === 'https:' && url.hostname === 'res.cloudinary.com' && !url.port && !url.username && !url.password ? url.href : '';} catch {return '';}
}
export function imageSize(image: string, width: number): string {
  return image.includes('/image/upload/') ? image.replace('/image/upload/', `/image/upload/f_auto,q_auto,w_${width},c_limit/`) : image;
}
export function parseCampuses(payload: unknown): Campus[] {
  if(!Array.isArray(row(payload).campuses))throw new Error('Invalid public campus response');
  return rows(row(payload).campuses).filter(c=>string(c.id) && string(c.slug)).map(c=>({id:string(c.id),name:string(c.name),slug:string(c.slug),isDefault:c.is_default===true}));
}
export function parseCategories(payload: unknown): Category[] {
  return rows(payload).filter(c=>c.is_active!==false && string(c.id)).map(c=>({id:string(c.id),name:string(c.name),slug:string(c.slug)}));
}
export function parseMeals(payload: unknown): Meal[] {
  if(!Array.isArray(row(payload).items))throw new Error('Invalid public menu response');
  return rows(row(payload).items).filter(m => string(m.id) && string(m.name) && m.is_secret!==true && !m.deleted_at && m.price!==null && m.price!=='' && Number.isFinite(Number(m.price)) && Number(m.price)>=0)
    .map(m=>({id:string(m.id),name:string(m.name),description:string(m.description),price:Number(m.price),image:safeImage(m.image_url),categoryId:string(m.category_id),available:m.is_available===true && m.is_sold_out!==true && (m.daily_remaining==null || Number(m.daily_remaining)>0)}));
}
export function parseHeroes(banners: unknown, sections: unknown): Hero[] {
  const found: Hero[]=[];
  for(const b of rows(banners).filter(b=>b.is_active!==false && (!b.placement || b.placement==='hero'))) {
    const slides=row(b.metadata).slides;
    const source: Row[]=Array.isArray(slides) ? rows(slides) : (Array.isArray(b.images) && b.images.length ? b.images : [b.image_url]).map(image=>({...b,image_url:typeof image==='string'?image:row(image).url}));
    for(const s of source) {
      const image=safeImage(s.image_url);
      if(!image && s.display_mode!=='text')continue;
      found.push({title:string(s.title),subtitle:string(s.subtitle),eyebrow:string(s.eyebrow)||string(row(b.metadata).eyebrow),image,mobileImage:safeImage(s.mobile_image_url),cta:string(s.cta_text)||string(b.action_label)||'View menu',destination:string(s.cta_url)||string(b.action_url)||'/menu'});
    }
  }
  if(found.length)return found;
  return rows(sections).filter(s=>s.is_active!==false && s.section_type==='hero').flatMap(s=>{
    const content=row(s.content);const image=safeImage(content.image_url||content.image||s.image_url);
    return image ? [{title:string(content.headline||content.title||s.title),subtitle:string(content.sub||content.body||content.subtitle),eyebrow:string(content.eyebrow),image,mobileImage:'',cta:string(content.cta||content.cta_text)||'View menu',destination:string(content.cta_url||content.cta_link)||'/menu'}] : [];
  });
}
export function filterMeals(meals: Meal[], query: string, category: string): Meal[] {
  const term=query.trim().toLocaleLowerCase();
  return meals.filter(m=>(!category||m.categoryId===category)&&(!term||`${m.name} ${m.description}`.toLocaleLowerCase().includes(term)));
}
export function previewPath(path: '/'|'/menu', campus?: string): string {
  return campus ? `${path}?${new URLSearchParams({campus})}` : path;
}
/** Internal preview destinations stay local; other relative links go to the live app. */
export function cmsDestination(value: string, liveOrigin: string, campus?: string): string {
  try {
    const url=new URL(value||'/menu',liveOrigin);
    if(url.origin!==liveOrigin)return previewPath('/menu',campus);
    if(url.pathname==='/' || url.pathname==='/menu')return previewPath(url.pathname,campus);
    return url.href;
  } catch {return previewPath('/menu',campus);}
}
