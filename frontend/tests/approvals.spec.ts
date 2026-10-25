import {test,expect,Browser,Page} from '@playwright/test';
import {selectProfile} from './profile-helpers';
const API='http://localhost:8000';
async function proposal(page:Page){
 const listings=await (await page.request.get(API+'/listings')).json();
 const item=listings.find((i:{title:string})=>i.title==='TI-84 Plus CE Graphing Calculator');
 let n=await (await page.request.post(API+'/negotiations',{data:{listing_id:item.id,target:'15',maximum:'25',rental_days:3,deadline:item.available_until,windows:item.windows,location:'Hayden Library',provider:'mock'}})).json();
 for(let turn=0;turn<9&&['Negotiating','Agreement proposed'].includes(n.status);turn++){
   n=await (await page.request.post(`${API}/negotiations/${n.id}/advance`,{data:{version:n.version}})).json();
 }
 expect(n.status).toBe('Awaiting approvals');return n;
}
async function sessions(browser:Browser){
 const a=await browser.newContext(),b=await browser.newContext();
 const buyer=await a.newPage(),seller=await b.newPage();
 await buyer.goto('/');await selectProfile(buyer,'Abbhijit');
 await seller.goto('/');await selectProfile(seller,'Shorya Moses');
 return {a,b,buyer,seller};
}
for(const order of ['buyer-first','seller-first']){
 test(`two isolated sessions receive live approvals, ${order}`,async({browser})=>{
  const {a,b,buyer,seller}=await sessions(browser);
  try{
   const n=await proposal(buyer);
   await buyer.goto('/?negotiation='+n.id);
   // The seller reaches the proposal through the existing participant-only history.
   await seller.getByRole('button',{name:'My negotiations',exact:true}).click();
   await seller.locator('.history-list>button').filter({hasText:`Deal #${n.id} ·`}).click();
   expect(new URL(seller.url()).searchParams.get('negotiation')).toBe(String(n.id));
   await expect(seller.locator('.participants')).toContainText('Abbhijit');
   await buyer.getByRole('button',{name:'Copy negotiation link'}).click();
   const link=await buyer.getByLabel('Negotiation link',{exact:true}).inputValue();
   expect(new URL(link).searchParams.toString()).toBe('negotiation='+n.id);
   expect(await seller.getByLabel('Demo student',{exact:true}).inputValue()).not.toBe(await buyer.getByLabel('Demo student',{exact:true}).inputValue());
   const first=order==='buyer-first'?buyer:seller,second=order==='buyer-first'?seller:buyer;
   await first.getByRole('button',{name:'Approve Deal',exact:true}).click();
   await expect(first.getByText('You approved this deal.',{exact:true})).toBeVisible();
   await expect(first.getByText(`Waiting for ${order==='buyer-first'?'Shorya Moses':'Abbhijit'} to approve.`,{exact:true})).toBeVisible();
   await expect(first.getByRole('button',{name:'Approve Deal',exact:true})).toHaveCount(0);
   await expect(second.locator('.approval-person').nth(order==='buyer-first'?0:1)).toContainText('Approved',{timeout:10000});
   await expect(second.getByRole('button',{name:'Approve Deal',exact:true})).toBeVisible();
   await second.getByRole('button',{name:'Approve Deal',exact:true}).click();
   for(const page of [first,second])await expect(page.getByRole('heading',{name:'Deal confirmed! Both students approved.',exact:true})).toBeVisible({timeout:10000});
   await first.reload();await expect(first.locator('.approval-state.state-approved')).toHaveCount(2);
   const outsider=await browser.newContext();
   try{
    const page=await outsider.newPage();await page.goto('/');await selectProfile(page,'Oumar');await page.goto(link);
    await expect(page.getByRole('button',{name:'Approve Deal'})).toHaveCount(0);
    expect((await page.request.post(`${API}/negotiations/${n.id}/approve`,{data:{decision:'approve',role:'buyer'}})).status()).toBe(403);
    expect((await page.request.get(API+'/demo/session')).ok()).toBeTruthy();
    await expect(page.getByLabel('Demo student',{exact:true}).locator('option:checked')).toHaveText('Oumar');
   }finally{await outsider.close()}
  }finally{await a.close();await b.close()}
 });
}
test('rejection appears in both sessions, blocks confirmation, and ends polling',async({browser})=>{
 const {a,b,buyer,seller}=await sessions(browser);
 try{
  const n=await proposal(buyer),path=`/negotiations/${n.id}`;
  await buyer.goto('/?negotiation='+n.id);await seller.goto('/?negotiation='+n.id);
  await buyer.getByRole('button',{name:'Approve Deal'}).click();
  await seller.getByRole('button',{name:'Reject Deal'}).click();
  for(const p of [buyer,seller]){
   await expect(p.getByRole('heading',{name:'This deal was rejected'})).toBeVisible({timeout:10000});
   await expect(p.locator('.terminal-navigation').getByRole('button')).toHaveCount(2);
   await expect(p.getByText('Shorya Moses rejected this deal. No further approvals are allowed.')).toBeVisible();
   await expect(p.getByRole('button',{name:'Approve Deal'})).toHaveCount(0);
  }
  expect((await buyer.request.post(API+path+'/approve',{data:{decision:'approve'}})).status()).toBe(409);
  let requests=0;buyer.on('request',r=>{if(r.url()===API+path&&r.method()==='GET')requests++});
  // Wait beyond one polling interval using the browser timer, then inspect network activity.
  await buyer.evaluate(()=>new Promise(resolve=>setTimeout(resolve,3000)));
  expect(requests).toBe(0);
 }finally{await a.close();await b.close()}
});
test('temporary polling failure recovers without losing the proposal',async({page})=>{
 await page.goto('/');await selectProfile(page,'Abbhijit');const n=await proposal(page);
 await page.goto('/?negotiation='+n.id);await expect(page.getByRole('button',{name:'Approve Deal'})).toBeVisible();
 let fail=true;
 await page.route(API+`/negotiations/${n.id}`,async route=>{if(fail)await route.fulfill({status:503,json:{detail:'Temporary test outage'}});else await route.continue()});
 await expect(page.getByText('Approval updates are temporarily unavailable. Retrying…')).toBeVisible({timeout:10000});
 await expect(page.locator('.deal-price')).toContainText('$');fail=false;
 await expect(page.getByText('Approval updates are temporarily unavailable. Retrying…')).toHaveCount(0,{timeout:10000});
});
