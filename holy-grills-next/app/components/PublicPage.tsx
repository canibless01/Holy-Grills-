import Link from 'next/link';
import Image from 'next/image';
import {APP_CONFIG} from '@/lib/config';
import {previewPath,type Campus} from '@/lib/public-model';
export function Shell({campus,children}:{campus?:Campus;children:React.ReactNode}) {
 return <><a className="skip" href="#main">Skip to content</a><div className="preview">Public-page preview · Ordering and account actions continue on the live site.</div>
 <header className="site-header"><Link href={previewPath('/',campus?.slug)} aria-label={`${APP_CONFIG.name} home`} prefetch={false}><Image src="/brand/wordmark.png" alt={APP_CONFIG.name} width={123} height={62} priority /></Link>
 <nav aria-label="Main navigation"><Link prefetch={false} href={previewPath('/',campus?.slug)}>Home</Link><Link prefetch={false} href={previewPath('/menu',campus?.slug)}>Menu</Link><a href={`${APP_CONFIG.liveOrigin}/orders`}>My orders →</a></nav></header>
 <main id="main">{children}</main><footer><strong>{APP_CONFIG.name}</strong><span>{APP_CONFIG.tagline}</span><a href={`${APP_CONFIG.liveOrigin}/our-story`}>Our story →</a><a href={`${APP_CONFIG.liveOrigin}/terms`}>Terms &amp; privacy →</a></footer></>;
}
export function Unavailable({path}:{path:'/'|'/menu'}) {
 return <section className="empty"><p className="eyebrow">Let’s try that again</p><h1>We couldn’t load the menu just now.</h1><p>Your connection or the service may need a moment. You can retry or continue on the live site.</p><div className="actions"><a href={path} className="button">Try again</a><a href={`${APP_CONFIG.liveOrigin}/menu`}>Open live menu →</a></div></section>;
}
