import {expect,Page} from '@playwright/test';
const API='http://localhost:8000';
export async function selectProfile(page:Page,name:string){
 const select=page.getByLabel('Demo profile',{exact:true});
 await expect(select).toBeEnabled();
 const profiles=await (await page.request.get(API+'/students')).json();
 const profile=profiles.find((p:{display_name:string})=>p.display_name===name);
 await select.selectOption(profile.id);
 await expect(select).toHaveValue(profile.id);
 return profile;
}
export async function newListing(page:Page,title:string){
 await page.getByRole('button',{name:'List an item',exact:true}).click();
 await page.getByLabel('Item name',{exact:true}).fill(title);
 await page.getByLabel('Description',{exact:true}).fill('A carefully maintained calculator for your next math exam. Includes charging cable.');
 await page.getByLabel('Asking price ($)',{exact:true}).fill('35');
 await page.getByLabel('Private minimum ($)',{exact:true}).fill('20');
 await page.getByRole('button',{name:'Publish listing'}).click();
 await expect(page.getByRole('button',{name:title,exact:true})).toBeVisible();
}
