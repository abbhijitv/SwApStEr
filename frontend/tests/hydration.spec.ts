import {test,expect} from '@playwright/test';
import {selectProfile} from './profile-helpers';

test('clean browser hydrates marketplace and persisted profiles without warnings',async({page})=>{
 const hydrationMessages:string[]=[];
 const errors:string[]=[];
 page.on('console',message=>{
   if(/hydrat|server.rendered|did not match|minified react error #(418|425)/i.test(message.text()))hydrationMessages.push(message.text());
 });
 page.on('pageerror',error=>errors.push(error.message));
 await page.goto('/');
 await expect(page.getByLabel('Demo student',{exact:true})).toBeEnabled();
 await expect(page.locator('.item-card').first()).toBeVisible();
 await selectProfile(page,'Oumar');
 await page.reload();
 await expect(page.getByLabel('Demo student',{exact:true}).locator('option:checked')).toHaveText('Oumar');
 await page.getByRole('button',{name:'My negotiations',exact:true}).click();
 await expect(page.getByRole('heading',{name:'My negotiations',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Back to marketplace'}).click();
 expect(hydrationMessages).toEqual([]);
 expect(errors).toEqual([]);
});
