import {mkdirSync,writeFileSync} from 'node:fs';
import {test,expect} from '@playwright/test';
import {selectProfile} from './profile-helpers';
test('real Ollama TI-84 proposal requires independent buyer and seller approvals',async({page,browser})=>{
 test.skip(process.env.RUN_OLLAMA_E2E!=='1','Opt in to local model inference');
 test.setTimeout(360000);
 const sellerContext=await browser.newContext();
 try{
  const seller=await sellerContext.newPage();
  await page.goto('/');await selectProfile(page,'Abbhijit');
  await seller.goto('/');await selectProfile(seller,'Shorya Moses');
  await page.getByRole('textbox',{name:'Search marketplace'}).fill('TI-84');
  await page.getByRole('button',{name:'View & negotiate'}).click();
  await page.getByRole('button',{name:'Let My AI Negotiate'}).click();
  await page.getByLabel('Target price ($)',{exact:true}).fill('15');
  await page.getByLabel('Agent provider').selectOption('ollama');
  await page.getByRole('button',{name:'Start AI negotiation'}).click();
  await expect(page.locator('.provider')).toHaveText('Ollama · Qwen 2.5 3B');
  await expect(page.locator('.agent-card').first()).toContainText('Abbhijit');
  await expect(page.locator('.seller-agent')).toContainText('Shorya Moses');
  const proposal=page.getByRole('button',{name:'Approve Deal',exact:true});
  await Promise.race([
   proposal.waitFor({state:'visible',timeout:300000}),
   page.getByText(/No agreement —/).first().waitFor({state:'visible',timeout:300000}).then(async()=>{
     throw new Error('Negotiation ended without agreement: '+await page.getByText(/No agreement —/).first().innerText());
   }),
   page.locator('.error').first().waitFor({state:'visible',timeout:300000}).then(async()=>{
     throw new Error(await page.locator('.error').first().innerText());
   })
  ]);
  const price=Number((await page.locator('.deal-price').innerText()).match(/\$([\d.]+)/)![1]);
  expect(price).toBeGreaterThanOrEqual(20);expect(price).toBeLessThanOrEqual(25);
  const id=new URL(page.url()).searchParams.get('negotiation');
  await page.getByRole('button',{name:'Approve Deal',exact:true}).click();
  await expect(page.getByText('You approved this deal.',{exact:true})).toBeVisible();
  await expect(page.getByRole('heading',{name:'Deal confirmed! Both students approved.',exact:true})).toHaveCount(0);
  await seller.getByRole('button',{name:'My negotiations',exact:true}).click();
  await seller.locator('.history-list>button').filter({hasText:`Deal #${id} ·`}).click();
  await expect(seller.locator('.approval-person').first()).toContainText('Approved');
  await seller.getByRole('button',{name:'Approve Deal',exact:true}).click();
  for(const p of [page,seller])await expect(p.getByRole('heading',{name:'Deal confirmed! Both students approved.',exact:true})).toBeVisible({timeout:10000});
  const record=await (await page.request.get(`http://localhost:8000/negotiations/${id}`)).json();
  mkdirSync('../artifacts',{recursive:true});writeFileSync('../artifacts/natural-ollama-transcript.json',JSON.stringify(record,null,2));
  await selectProfile(seller,'Oumar');
  expect((await seller.request.post(`http://localhost:8000/negotiations/${id}/approve`,{data:{decision:'approve'}})).status()).toBe(403);
  await expect(page.getByLabel('Demo student',{exact:true}).locator('option:checked')).toHaveText('Abbhijit');
  await page.screenshot({path:'../artifacts/ollama-two-student-confirmed.png',fullPage:true});
 }finally{await sellerContext.close()}
});
