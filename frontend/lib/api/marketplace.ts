import type {SupabaseClient} from '@supabase/supabase-js';
import {accountRequest, AccountApiError} from './authenticated';
import type {Housing} from '../../app/housing';
export {AccountApiError};
export type Window = {start:string; end:string};
export type ListingInput = {title:string;description:string;category:string;course:string;condition:string;price:string;minimum:string;type:'Rent'|'Buy';rental_days?:number;windows:Window[];available_until:string|null;restrictions:string;housing:Housing|null};
export type Listing = Omit<ListingInput,'minimum'> & {id:number;version:number;seller:string;rental_days:number};
export type OwnListing = Listing & {minimum:string;seller_id:string;deleted:boolean};
export type Terms = {price:string;location:string;pickup?:string;return_date?:string;rental_days?:number;lease_start?:string;lease_end?:string;transaction?:string};
export type Negotiation = {id:number;listing_id:number;item:Listing;version:number;status:string;provider:'mock'|'ollama';turn:number;turn_limit?:number;buyer_id:string;seller_id:string;approvals:Record<string,boolean>;messages:{role:string;action:string;text:string;timestamp:string;terms:Terms|null}[];offer:Terms|null;agreement:Terms|null;reason?:string;error?:string|null};
export type Preferences = {listing_id:number;target?:string;maximum:string;rental_days?:number;windows?:Window[];deadline?:string;location?:string;provider:'mock'|'ollama';housing?:{desired_move_in:string;desired_move_out:string;preferred_location:string;furnished:boolean|null;utilities_included:boolean|null;move_in_flex_days:number;requirements:string}};
export function marketplace(client:SupabaseClient|null) {
  const call=<T>(path:string,method='GET',body?:unknown,publicRead=false)=>accountRequest<T>(client,'/marketplace'+path,{method,body:body===undefined?undefined:JSON.stringify(body)},publicRead);
  return {
    browse:(after=0)=>call<Listing[]>('/listings?limit=50&after='+after,'GET',undefined,true),
    listing:(id:number)=>call<Listing>('/listings/'+id,'GET',undefined,true),
    mine:(after=0)=>call<OwnListing[]>('/listings/mine?include_deleted=true&limit=50&after='+after),
    manage:(id:number)=>call<OwnListing>(`/listings/${id}/manage`),
    create:(input:ListingInput)=>call<OwnListing>('/listings','POST',input),
    edit:(id:number,input:ListingInput,version:number)=>call<OwnListing>('/listings/'+id,'PUT',{...input,version}),
    remove:(id:number,version:number)=>call<void>(`/listings/${id}?version=${version}`,'DELETE'),
    history:(after=0)=>call<Negotiation[]>('/negotiations?limit=50&after='+after),
    negotiation:(id:number)=>call<Negotiation>('/negotiations/'+id),
    start:(input:Preferences)=>call<Negotiation>('/negotiations','POST',input),
    advance:(n:Pick<Negotiation,'id'|'version'>)=>call<Negotiation>(`/negotiations/${n.id}/advance`,'POST',{version:n.version}),
    decide:(n:Pick<Negotiation,'id'|'version'>,decision:'approve'|'reject')=>call<Negotiation>(`/negotiations/${n.id}/approve`,'POST',{version:n.version,decision}),
    cancel:(n:Pick<Negotiation,'id'|'version'>)=>call<Negotiation>(`/negotiations/${n.id}/cancel`,'POST',{version:n.version}),
  };
}
