import Image from 'next/image';
import Link from 'next/link';
import {notFound} from 'next/navigation';
import {Shell,Unavailable} from './components/PublicPage';
import MealGrid from './components/MealGrid';
import {getCampuses,getHeroes,getMenu,reportPublicFailure} from '@/lib/public-api';
import {APP_CONFIG} from '@/lib/config';
import {cmsDestination,imageSize,previewPath,type Campus,type Hero,type Meal} from '@/lib/public-model';
export const dynamic='force-dynamic';
export default async function Home({searchParams}:{searchParams:Promise<{campus?:string}>}) {
 const params=await searchParams;let campuses:Campus[];
 try{campuses=await getCampuses();}catch(error){reportPublicFailure(error);return <Shell><Unavailable path="/" /></Shell>;}
 const campus=params.campus?campuses.find(c=>c.slug===params.campus):campuses.find(c=>c.isDefault)||campuses[0];
 if(params.campus&&!campus)notFound();
 if(!campus)return <Shell><Unavailable path="/" /></Shell>;
 let heroes:Hero[]=[],items:Meal[]=[];
 try{[heroes,{items}]=await Promise.all([getHeroes(campus.id),getMenu(campus.id)]);}catch(error){reportPublicFailure(error);return <Shell campus={campus}><Unavailable path="/" /></Shell>;}
 return <Shell campus={campus}>
 {heroes.length?<section className="hero-strip" aria-label="From the grill">{heroes.map((hero,i)=><article className={`hero ${hero.image?'':'text-hero'}`} id={`slide-${i+1}`} key={i}>
 {hero.image?<picture>{hero.mobileImage?<source media="(max-width: 640px)" srcSet={imageSize(hero.mobileImage,900)} />:null}<Image src={imageSize(hero.image,1600)} alt="" fill sizes="100vw" unoptimized priority={i===0} loading={i===0?'eager':'lazy'} /></picture>:null}
 <div className="hero-shade" /><div className="hero-copy">{hero.eyebrow?<p className="hero-eyebrow">{hero.eyebrow}</p>:null}{i===0?<h1>{hero.title||APP_CONFIG.tagline}</h1>:<h2>{hero.title}</h2>}<p>{hero.subtitle}</p><a className="button" href={cmsDestination(hero.destination,APP_CONFIG.liveOrigin,campus.slug)}>{hero.cta}</a>
 <nav className="hero-dots" aria-label="Hero slides">{heroes.map((_,n)=><a key={n} href={`#slide-${n+1}`} aria-label={`Show slide ${n+1}`} aria-current={n===i?'true':undefined}>{n+1}</a>)}</nav></div></article>)}</section>:<section className="empty"><h1>{APP_CONFIG.tagline}</h1><Link className="button" href={previewPath('/menu',campus.slug)}>View menu</Link></section>}
 <section className="content"><div className="section-heading"><div><p className="eyebrow">{campus.name}</p><h2>Fresh off the grill</h2></div><Link className="text-link" href={previewPath('/menu',campus.slug)} prefetch={false}>Explore the menu →</Link></div>
 <MealGrid items={items.slice(0,6)} /></section>
 </Shell>;
}
