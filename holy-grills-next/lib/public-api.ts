import 'server-only';
import {cache} from 'react';
import {parseCampuses,parseCategories,parseMeals,parseHeroes} from './public-model';
export class PublicDataError extends Error {}
/** Fixed allowlist: this pilot cannot proxy authenticated or money-changing endpoints. */
const PATHS=new Set(['campuses','menu/items','menu/categories','storefront/banners','storefront/sections']);
async function get(path: string, campusId?: string, fresh=false): Promise<unknown> {
  if(!PATHS.has(path))throw new PublicDataError('Unsupported public resource');
  const base=process.env.API_BASE_URL;
  if(!base)throw new PublicDataError('Public API is not configured');
  const url=new URL(`${base.replace(/\/$/,'')}/${path}`);
  if(!['https:','http:'].includes(url.protocol))throw new PublicDataError('Invalid API configuration');
  if(campusId)url.searchParams.set('campus_id',campusId);
  const response=await fetch(url,{
    method:'GET',credentials:'omit',redirect:'error',
    headers:{Accept:'application/json',...(campusId?{'X-Campus-ID':campusId}:{})},
    signal:AbortSignal.timeout(7000),
    ...(fresh?{cache:'no-store' as const}:{next:{revalidate:30}}),
  });
  if(!response.ok)throw new PublicDataError(`Public ${path} returned ${response.status}`);
  return response.json();
}
export const getCampuses=cache(async()=>parseCampuses(await get('campuses')));
export const getMenu=cache(async(campusId:string)=>{
  // Availability/prices are never served from a Next data cache. Campus is in URL and header.
  const [items,categories]=await Promise.all([get('menu/items',campusId,true),get('menu/categories',campusId)]);
  return {items:parseMeals(items),categories:parseCategories(categories)};
});
export const getHeroes=cache(async(campusId:string)=>{
  // CMS failure must not erase an otherwise available menu.
  const [banners,sections]=await Promise.allSettled([get('storefront/banners',campusId),get('storefront/sections',campusId)]);
  return parseHeroes(banners.status==='fulfilled'?banners.value:[],sections.status==='fulfilled'?sections.value:[]);
});

export function reportPublicFailure(error: unknown): void {
  console.warn('[public-pilot] read failed', error instanceof PublicDataError ? error.message : error instanceof Error ? error.name : 'unknown');
}
