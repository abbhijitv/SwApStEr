import {AccountApiError,type Negotiation} from './marketplace';

type AgentApi = {negotiation:(id:number)=>Promise<Negotiation>;advance:(n:Negotiation)=>Promise<Negotiation>};
type Options = {signal:AbortSignal;onState:(n:Negotiation)=>void;wait?:()=>Promise<void>};
/** Bounded client orchestration. Every retry starts from authoritative server state.
 * Aborting stops scheduling, not an already committed server request.
 * This runner never prepares human review or submits a human decision.
 */
export async function runNegotiation(api:AgentApi,id:number,{signal,onState,wait=()=>new Promise(resolve=>setTimeout(resolve,650))}:Options) {
  for(let attempts=0;attempts<8&&!signal.aborted;attempts++){
    const current=await api.negotiation(id);
    if(signal.aborted)return;
    onState(current);
    if(current.status!=='Negotiating'||current.error)return;
    if(current.turn>=Math.min(8,current.turn_limit??8))throw new AccountApiError('conflict','The agent turn limit was reached. Refresh to review the final server state.');
    try {
      const latest=await api.advance(current);
      if(signal.aborted)return;
      onState(latest);
      if(latest.status!=='Negotiating'||latest.error)return;
    }catch(error){
      if(!(error instanceof AccountApiError)||error.kind!=='conflict')throw error;
      // Another tab may have committed this version. Never resend it.
    }
    if(!signal.aborted)await wait();
  }
  if(!signal.aborted)throw new AccountApiError('conflict','Automatic progress paused after its request limit. Refresh and review before resuming.');
}
