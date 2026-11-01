import {test,expect} from '@playwright/test';
import type {SupabaseClient} from '@supabase/supabase-js';
import {marketplace,AccountApiError,type ListingInput} from '../lib/api/marketplace';
let original:typeof fetch;let base:string|undefined;
const client={auth:{getSession:async()=>({data:{session:{access_token:'synthetic-user-access'}},error:null})}} as unknown as SupabaseClient;
test.beforeEach(()=>{original=global.fetch;base=process.env.NEXT_PUBLIC_API_URL;process.env.NEXT_PUBLIC_API_URL='https://api.example.invalid'});
test.afterEach(()=>{global.fetch=original;if(base===undefined)delete process.env.NEXT_PUBLIC_API_URL;else process.env.NEXT_PUBLIC_API_URL=base});
test('public reads omit tokens and demo cookies, protected requests use only current token',async()=>{
 const calls:{url:string;init:RequestInit}[]=[];
 global.fetch=async(input,init)=>{calls.push({url:String(input),init:init!});return Response.json([])};
 const api=marketplace(client);await api.browse();await api.mine();await api.history();
 expect(calls[0].url).toBe('https://api.example.invalid/marketplace/listings?limit=50&after=0');
 expect(new Headers(calls[0].init.headers).has('Authorization')).toBe(false);
 for(const call of calls){expect(call.init.credentials).toBe('omit');expect(call.init.cache).toBe('no-store');expect(call.init.redirect).toBe('error')}
 expect(new Headers(calls[1].init.headers).get('Authorization')).toBe('Bearer synthetic-user-access');
});
test('listing operations use actual backend methods and versions',async()=>{
 const calls:{url:string;init:RequestInit}[]=[];
 global.fetch=async(input,init)=>{calls.push({url:String(input),init:init!});return init?.method==='DELETE'?new Response(null,{status:204}):Response.json({id:4,version:1})};
 const api=marketplace(client);await api.create({title:'Test'} as ListingInput);await api.manage(4);await api.edit(4,{title:'Changed'} as ListingInput,1);await api.remove(4,2);
 expect(calls.map(c=>c.init.method)).toEqual(['POST','GET','PUT','DELETE']);expect(JSON.parse(String(calls[2].init.body))).toEqual({title:'Changed',version:1});expect(calls[3].url).toContain('/listings/4?version=2');
});
test('decisions never contain a browser-supplied actor or counterpart approval',async()=>{
 const bodies:unknown[]=[];global.fetch=async(_,init)=>{bodies.push(JSON.parse(String(init?.body)));return Response.json({})};
 const n={id:5,version:9,buyer_id:'buyer',seller_id:'seller',approvals:{buyer:false,seller:false}};
 await marketplace(client).decide(n,'approve');await marketplace(client).decide(n,'reject');await marketplace(client).advance(n);await marketplace(client).cancel(n);
 expect(bodies).toEqual([{version:9,decision:'approve'},{version:9,decision:'reject'},{version:9},{version:9}]);
});
for(const [status,kind] of [[401,'unauthorized'],[403,'forbidden'],[409,'conflict'],[422,'validation'],[404,'missing'],[503,'unavailable']] as const){test(`status ${status} is distinct and never echoes private server details`,async()=>{let count=0;global.fetch=async()=>{count++;return Response.json({detail:'private maximum 123.45'}, {status})};try{await marketplace(client).history();throw Error('Expected rejection')}catch(error){expect(error).toBeInstanceOf(AccountApiError);expect((error as AccountApiError).kind).toBe(kind);expect((error as Error).message).not.toContain('123.45')}expect(count).toBe(1)})}
test('feature disabled and network failure have actionable distinct errors',async()=>{
 global.fetch=async()=>Response.json({detail:'Account marketplace is not enabled.'},{status:404});await expect(marketplace(null).browse()).rejects.toMatchObject({kind:'disabled'});
 global.fetch=async()=>{throw Error('sensitive upstream')};await expect(marketplace(null).browse()).rejects.toMatchObject({kind:'network'});
});
test('missing and expired sessions fail before protected fetch without demo fallback',async()=>{
 let count=0;global.fetch=async()=>{count++;return Response.json({})};await expect(marketplace(null).mine()).rejects.toMatchObject({kind:'unauthorized'});
 const expired={auth:{getSession:async()=>({data:{session:null},error:null})}} as unknown as SupabaseClient;
 await expect(marketplace(expired).history()).rejects.toMatchObject({kind:'unauthorized'});expect(count).toBe(0);
});
