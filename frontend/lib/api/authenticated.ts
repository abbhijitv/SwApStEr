import type {SupabaseClient} from '@supabase/supabase-js';
export type AccountUser = {id: string; role: 'authenticated'};
export class AccountApiError extends Error {
  constructor(public kind:'unauthorized'|'forbidden'|'conflict'|'validation'|'disabled'|'missing'|'network'|'unavailable', message:string) {super(message);}
}
/** Account-only transport: no demo cookies, identity parameters, retries or storage. */
export async function accountRequest<T>(client:SupabaseClient|null,path:string,init:RequestInit={},publicRead=false):Promise<T> {
  let token:string|undefined;
  if (!publicRead) {
    if (!client) throw new AccountApiError('unauthorized','Sign in to continue.');
    try {const {data,error}=await client.auth.getSession(); if (!error) token=data.session?.access_token;}
    catch {throw new AccountApiError('unauthorized','Your session is invalid or expired. Sign in again.');}
    if (!token) throw new AccountApiError('unauthorized','Your session is invalid or expired. Sign in again.');
  }
  let base:URL;
  try {base=new URL(process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000');}
  catch {throw new AccountApiError('unavailable','Configure a secure account API URL.');}
  const local=process.env.NODE_ENV!=='production' && ['localhost','127.0.0.1','[::1]'].includes(base.hostname);
  if ((base.protocol!=='https:' && !(local && base.protocol==='http:')) || base.username || base.password || base.search || base.hash) throw new AccountApiError('unavailable','Configure a secure account API URL.');
  const headers=new Headers(init.headers);
  if(token) headers.set('Authorization','Bearer '+token);
  if(init.body) headers.set('Content-Type','application/json');
  let response:Response;
  try {response=await fetch(base.toString().replace(/\/$/,'')+path,{...init,headers,credentials:'omit',cache:'no-store',redirect:'error'});}
  catch {throw new AccountApiError('network','Cannot reach the account API. Check your connection and retry.');}
  if (!response.ok) {
    const errors:Record<number,[AccountApiError['kind'],string]>={
      401:['unauthorized','Your session is invalid or expired. Sign in again.'],
      403:['forbidden','You do not have permission to perform this action.'],
      409:['conflict','This record changed or the action is no longer available. Refresh and review before trying again.'],
      422:['validation','Please check your fields, dates, price limits and rental duration.'],
      404:['missing','This record is unavailable or you do not have access.'],
    };
    if(response.status===404){const body=await response.json().catch(()=>null);if(body?.detail==='Account marketplace is not enabled.')throw new AccountApiError('disabled','Real marketplace is unavailable. For local testing, enable ENABLE_ACCOUNT_MARKETPLACE on the backend.');}
    const [kind,message]=errors[response.status] || ['unavailable','Account authentication or marketplace service is unavailable.'];
    throw new AccountApiError(kind,message);
  }
  return response.status===204 ? undefined as T : response.json();
}
export function getAccountUser(client:SupabaseClient):Promise<AccountUser> {return accountRequest(client,'/auth/me');}
