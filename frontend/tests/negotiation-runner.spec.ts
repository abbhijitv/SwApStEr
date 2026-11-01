import {test,expect} from '@playwright/test';
import {runNegotiation} from '../lib/api/negotiation-runner';
import {AccountApiError,type Negotiation} from '../lib/api/marketplace';
const state=(turn=0,status='Negotiating')=>({id:1,version:turn,turn,status,turn_limit:8,error:null} as Negotiation);
const wait=async()=>{};
test('automatically stops at proposal without preparing review or approving',async()=>{
 let current=state();const versions:number[]=[],seen:Negotiation[]=[];
 await runNegotiation({negotiation:async()=>current,advance:async n=>{versions.push(n.version);current=state(n.turn+1,n.turn===2?'Agreement proposed':'Negotiating');return current}},1,{signal:new AbortController().signal,onState:n=>seen.push(n),wait});
 expect(versions).toEqual([0,1,2]);expect(seen.at(-1)?.status).toBe('Agreement proposed');
});
test('stops on terminal no-agreement at the backend turn limit',async()=>{
 let current=state();const versions:number[]=[];
 await runNegotiation({negotiation:async()=>current,advance:async n=>{versions.push(n.version);current=state(n.turn+1,n.turn===7?'No agreement':'Negotiating');return current}},1,{signal:new AbortController().signal,onState:()=>{},wait});expect(versions).toEqual([0,1,2,3,4,5,6,7]);
});
test('does not advance a stale state already at its configured turn limit',async()=>{
 let calls=0;await expect(runNegotiation({negotiation:async()=>({...state(4),turn_limit:4}),advance:async n=>{calls++;return n}},1,{signal:new AbortController().signal,onState:()=>{},wait})).rejects.toMatchObject({kind:'conflict'});expect(calls).toBe(0);
});
test('conflict reloads current server version instead of resending old turns',async()=>{
 let current=state();const versions:number[]=[];
 await runNegotiation({negotiation:async()=>current,advance:async n=>{versions.push(n.version);if(n.version===0){current=state(1);throw new AccountApiError('conflict','Changed')}current=state(2,'Agreement proposed');return current}},1,{signal:new AbortController().signal,onState:()=>{},wait});expect(versions).toEqual([0,1]);
});
test('refresh after uncertain network failure resumes from committed server version',async()=>{
 let current=state();let fail=true;const versions:number[]=[];
 const api={negotiation:async()=>current,advance:async(n:Negotiation)=>{versions.push(n.version);current=state(n.turn+1,n.turn===1?'Agreement proposed':'Negotiating');if(fail){fail=false;throw new AccountApiError('network','Disconnected')}return current}};
 await expect(runNegotiation(api,1,{signal:new AbortController().signal,onState:()=>{},wait})).rejects.toMatchObject({kind:'network'});
 await runNegotiation(api,1,{signal:new AbortController().signal,onState:()=>{},wait});expect(versions).toEqual([0,1]);
});
test('pause stops scheduling even if an in-flight turn commits; resume reads it first',async()=>{
 const controller=new AbortController();let current=state();const versions:number[]=[];
 const api={negotiation:async()=>current,advance:async(n:Negotiation)=>{versions.push(n.version);current=state(n.turn+1,n.turn===1?'Agreement proposed':'Negotiating');controller.abort();return current}};
 await runNegotiation(api,1,{signal:controller.signal,onState:()=>{},wait});expect(versions).toEqual([0]);
 await runNegotiation(api,1,{signal:new AbortController().signal,onState:()=>{},wait});expect(versions).toEqual([0,1]);
});
for(const status of ['Cancelled','Rejected','Confirmed','No agreement','Awaiting approvals','Agreement proposed'])test(`never progresses ${status}`,async()=>{let calls=0;await runNegotiation({negotiation:async()=>state(2,status),advance:async n=>{calls++;return n}},1,{signal:new AbortController().signal,onState:()=>{},wait});expect(calls).toBe(0)});
test('provider error stops without automatic retries',async()=>{let calls=0;await runNegotiation({negotiation:async()=>({...state(),error:'Unavailable'}),advance:async n=>{calls++;return n}},1,{signal:new AbortController().signal,onState:()=>{},wait});expect(calls).toBe(0)});
test('repeated conflicts are bounded to eight requests',async()=>{let calls=0;await expect(runNegotiation({negotiation:async()=>state(),advance:async()=>{calls++;throw new AccountApiError('conflict','Changed')}},1,{signal:new AbortController().signal,onState:()=>{},wait})).rejects.toMatchObject({kind:'conflict'});expect(calls).toBe(8)});
