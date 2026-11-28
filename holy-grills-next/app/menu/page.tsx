import {notFound} from 'next/navigation';
import {Shell,Unavailable} from '../components/PublicPage';
import MealGrid from '../components/MealGrid';
import {getCampuses,getMenu,reportPublicFailure} from '@/lib/public-api';
import {filterMeals,type Campus} from '@/lib/public-model';
export const dynamic='force-dynamic';
export const metadata={title:'Menu preview — flame-grilled meals'};
export default async function Menu({searchParams}:{searchParams:Promise<{campus?:string;q?:string;category?:string}>}) {
 const params=await searchParams;let campuses:Campus[];
 try{campuses=await getCampuses();}catch(error){reportPublicFailure(error);return <Shell><Unavailable path="/menu" /></Shell>;}
 const campus=params.campus?campuses.find(c=>c.slug===params.campus):campuses.find(c=>c.isDefault)||campuses[0];
 if(params.campus&&!campus)notFound();
 if(!campus)return <Shell><Unavailable path="/menu" /></Shell>;
 let menu:Awaited<ReturnType<typeof getMenu>>;
 try{menu=await getMenu(campus.id);}catch(error){reportPublicFailure(error);return <Shell campus={campus}><Unavailable path="/menu" /></Shell>;}
 const query=typeof params.q==='string'?params.q.slice(0,160):'';
 const category=typeof params.category==='string'?params.category:'';
 const items=filterMeals(menu.items,query,category);
 return <Shell campus={campus}><section className="content menu-content"><p className="eyebrow">Today’s menu · {campus.name}</p><h1>Fresh off the grill</h1><p className="intro">Order for your table.</p>
 <form className="filters" action="/menu" method="get"><label>Campus<select aria-label="Campus" name="campus" defaultValue={campus.slug}>{campuses.map(c=><option key={c.id} value={c.slug}>{c.name}</option>)}</select></label><label className="search">Search the menu<input type="search" name="q" defaultValue={query} placeholder="Meal, side or something to share…" maxLength={160} /></label><label>Category<select aria-label="Category" name="category" defaultValue={category}><option value="">All items</option>{menu.categories.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label><button className="button" type="submit">Find a meal</button></form>
 <p className="result-count" role="status">{items.length} {items.length===1?'meal':'meals'}{query?` matching “${query}”`:''}</p>
 {items.length?<MealGrid items={items} />:<div className="empty compact"><h2>No meals match those filters.</h2><a href={`/menu?${new URLSearchParams({campus:campus.slug})}`}>View all meals</a></div>}
 <p className="handoff-note">Choose options on the live site to confirm your campus, availability and order total before paying.</p>
 </section></Shell>;
}
