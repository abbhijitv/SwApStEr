import {test,expect,Page} from '@playwright/test';
const students=[{id:'student-a',display_name:'Abbhijit'},{id:'student-b',display_name:'Shorya Moses'},{id:'student-c',display_name:'Oumar'}];
const base={description:'Photo presentation fixture; no database changes.',course:'MAT 265',condition:'Like new',price:'35',type:'Rent',rental_days:3,windows:[{start:'2027-06-01T16:00:00-07:00',end:'2027-06-01T20:00:00-07:00'}],available_until:'2027-06-10T20:00:00-07:00',seller:'Shorya Moses',seller_id:'student-b',icon:'calculator',restrictions:'Return in the same condition.'};
const groups=[['Calculators','TI-84 Plus CE'],['Calculators','TI-Nspire CX CAS'],['Textbooks','Calculus textbook'],['Lab kits','Arduino starter kit'],['Drafting','Engineering drafting tools'],['Housing & Subleases','Apartment sublease'],['Housing & Subleases','Private room sublease'],['Housing & Subleases','Room rental']];
const listings=groups.flatMap(([category,title],i)=>[1,2].map(variant=>({...base,id:i*2+variant,title:`${title} ${variant}`,category,...(category==='Housing & Subleases'?{price:'900',course:'',housing:{listing_type:title,neighborhood:'Tempe campus',lease_start:'2027-05-15',lease_end:'2027-08-15',furnished:true,utilities_included:true,bedrooms:1,bathrooms:1,roommate_info:''}}:{})})));
async function fixtures(page:Page){
 let student='student-a';
 const terms={price:'25',pickup:'2027-06-01T17:00:00-07:00',location:'Hayden Library',rental_days:3,return_date:'2027-06-04T17:00:00-07:00'};
 const n={id:99,item:listings[0],listing_id:1,status:'Awaiting approvals',provider:'mock',turn:2,version:2,messages:[{role:'buyer',action:'OFFER',text:'Would $25 work for three days?',terms,timestamp:'2027-05-01T12:00:00Z'},{role:'seller',action:'ACCEPT',text:'$25 works; both students still need to approve.',terms,timestamp:'2027-05-01T12:00:01Z'}],offer:terms,agreement:terms,approvals:{'student-a':false,'student-b':false},buyer:'Abbhijit',seller:'Shorya Moses',buyer_id:'student-a',seller_id:'student-b',created_at:'2027-05-01T12:00:00Z'};
 // All API traffic stays in this fixture: these visual tests never write live data.
 await page.route('http://localhost:8000/**',async route=>{
  const path=new URL(route.request().url()).pathname;
  if(path==='/students')return route.fulfill({json:students});
  if(path==='/listings')return route.fulfill({json:listings});
  if(path==='/demo/session'){
   if(route.request().method()==='POST')student=route.request().postDataJSON().student;
   return route.fulfill({json:{student,profile:students.find(s=>s.id===student)}});
  }
  if(path==='/negotiations/99/approve'){
   n.approvals[student as keyof typeof n.approvals]=true;n.version++;
   if(Object.values(n.approvals).every(Boolean))n.status='Confirmed';
   return route.fulfill({json:n});
  }
  if(path==='/negotiations/99')return route.fulfill({json:n});
  if(path==='/negotiations')return route.fulfill({json:[n]});
  return route.fulfill({status:404,json:{detail:'Unknown fixture endpoint'}});
 });
}
test('all photo groups load, keep stable sources after refresh, and fit desktop/mobile',async({page})=>{
 await page.setViewportSize({width:1440,height:1000});
 await fixtures(page);const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/marketplace');await expect(page.locator('.item-card')).toHaveCount(16);
 const photos=page.locator('.item-card .listing-photo img');
 for(const photo of await photos.all()){await photo.scrollIntoViewIfNeeded();await expect.poll(()=>photo.evaluate((img:HTMLImageElement)=>img.complete&&img.naturalWidth>0&&getComputedStyle(img).opacity==='1')).toBeTruthy()}
 const before=await photos.evaluateAll(images=>images.map(img=>img.getAttribute('src')));
 expect(new Set(before).size).toBe(16);
 for(const group of ['ti84','nspire','books','electronics','drafting','apartment','private-room','room-rental'])await expect(page.locator(`[data-photo-group="${group}"]`)).toHaveCount(2);
 await expect(page.locator('.item-card .illustrative-label')).toHaveCount(16);
 await page.reload();await expect(page.locator('.item-card')).toHaveCount(16);
 expect(await photos.evaluateAll(images=>images.map(img=>img.getAttribute('src')))).toEqual(before);
 for(const photo of await photos.all()){await photo.scrollIntoViewIfNeeded();await expect.poll(()=>photo.evaluate((img:HTMLImageElement)=>img.complete&&img.naturalWidth>0&&getComputedStyle(img).opacity==='1')).toBeTruthy()}
 await page.locator('#marketplace').evaluate(el=>el.scrollIntoView({block:'start',behavior:'instant'}));
 await page.screenshot({path:'../artifacts/photography/after-desktop.png'});
 await page.getByRole('button',{name:'Housing & Subleases',exact:true}).click();
 await expect(page.locator('.item-card')).toHaveCount(6);
 for(const photo of await photos.all()){await photo.scrollIntoViewIfNeeded();await expect.poll(()=>photo.evaluate((img:HTMLImageElement)=>img.complete&&img.naturalWidth>0&&getComputedStyle(img).opacity==='1')).toBeTruthy()}
 await page.locator('#marketplace').evaluate(el=>el.scrollIntoView({block:'start',behavior:'instant'}));await page.screenshot({path:'../artifacts/photography/after-housing-desktop.png'});
 await page.setViewportSize({width:390,height:844});await page.locator('.filters').evaluate(el=>el.scrollIntoView({block:'start',behavior:'instant'}));
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
 await page.screenshot({path:'../artifacts/photography/after-housing-mobile.png'});
 await page.getByRole('button',{name:'Apartment sublease 1',exact:true}).click();
 await expect(page.getByRole('dialog').getByRole('img',{name:/^Illustrative photo:/})).toBeVisible();
 await expect(page.getByRole('dialog')).toContainText('Illustrative photo');
 await expect(page.getByRole('dialog')).toContainText('/month');
 expect(errors).toEqual([]);
});
test('broken image shows category fallback without retry loops',async({page})=>{
 await fixtures(page);await page.route('**/_next/image?*',route=>route.abort());await page.goto('/marketplace');
 const first=page.locator('.item-card').first();await first.scrollIntoViewIfNeeded();
 await expect(first.locator('.photo-fallback')).toContainText('Calculators photo unavailable');
 await expect(first.locator('img')).toHaveCount(0);
});
test('photo summary preserves independent buyer and seller approval controls',async({page})=>{
 await fixtures(page);await page.goto('/marketplace?negotiation=99');
 await expect(page.locator('.summary .listing-photo img')).toBeVisible();
 await page.getByRole('button',{name:'Approve Deal',exact:true}).click();
 await expect(page.getByText('You approved this deal.',{exact:true})).toBeVisible();
 await expect(page.getByRole('heading',{name:'Deal confirmed! Both people approved.',exact:true})).toHaveCount(0);
 await page.getByRole('button',{name:'Demo: Switch to seller',exact:true}).click();
 await page.getByRole('button',{name:'Approve Deal',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Deal confirmed! Both people approved.',exact:true})).toBeVisible();
});
