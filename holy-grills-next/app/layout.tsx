import localFont from 'next/font/local';
import type {Metadata} from 'next';
import {APP_CONFIG} from '@/lib/config';
import './globals.css';
const nunito=localFont({src:'../public/fonts/nunito-latin-wght-normal.woff2',variable:'--font-nunito',display:'swap'});
export const metadata:Metadata={
 title:{default:`${APP_CONFIG.name} — Public preview`,template:`%s | ${APP_CONFIG.name}`},
 description:APP_CONFIG.description,
 robots:{index:false,follow:false},
};
export default function RootLayout({children}:{children:React.ReactNode}) {
 return <html lang="en"><body className={nunito.variable}>{children}</body></html>;
}
