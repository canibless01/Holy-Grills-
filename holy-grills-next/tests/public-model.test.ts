import {test} from 'node:test';
import assert from 'node:assert/strict';
import {parseCampuses,parseMeals,parseHeroes,filterMeals,cmsDestination,safeImage,previewPath} from '../lib/public-model.ts';
const sample={id:'one',name:'Wing plate',description:'Chips and chicken',price:2500,is_available:true,category_id:'plates'};
test('public DTO excludes internal prices, reward rules and contacts',()=>{
 const [meal]=parseMeals({items:[{...sample,cushion_amount:900,cushion_snapshot:900,user_email:'private@example.com',hp_earn:50,options:{private:'secret'}}]});
 assert.equal(meal.price,2500);assert.deepEqual(Object.keys(meal).sort(),['available','categoryId','description','id','image','name','price'].sort());
});
test('invalid response shapes are failures, not a fabricated empty menu',()=>{
 assert.throws(()=>parseMeals({error:'failed'}));assert.throws(()=>parseCampuses({error:'failed'}));
 assert.deepEqual(parseMeals({items:[]}),[]);
});
test('secret/deleted and invalid-price items never enter the public grid',()=>{
 const invalid=[{is_secret:true},{deleted_at:'today'},{price:-1},{price:null},{price:'no'},{price:''},{price:undefined}];
 assert.equal(parseMeals({items:invalid.map(v=>({...sample,...v}))}).length,0);
});
test('zero price stays valid; sold-out and exhausted items cannot offer ordering links',()=>{
 const items=parseMeals({items:[{...sample,price:0},{...sample,id:'two',is_sold_out:true},{...sample,id:'three',daily_remaining:0},{...sample,id:'four',is_available:false}]});
 assert.equal(items[0].price,0);assert.deepEqual(items.map(i=>i.available),[true,false,false,false]);
});
test('search and category filters compose without case sensitivity',()=>{
 const items=parseMeals({items:[sample,{...sample,id:'two',name:'Skewer',description:'Beef',category_id:'skewers'}]});
 assert.equal(filterMeals(items,' CHICKEN ','plates').length,1);assert.equal(filterMeals(items,'beef','plates').length,0);
});
test('CMS scripts, tracking URLs and credentialed images are not rendered',()=>{
 assert.equal(safeImage('javascript:alert(1)'), '');assert.equal(safeImage('https://evil.test/a.jpg'),'');assert.equal(safeImage('https://x:password@res.cloudinary.com/a.jpg'),'');assert.equal(safeImage('https://res.cloudinary.com:444/a.jpg'),'');
 assert.equal(cmsDestination('javascript:alert(1)','https://holygrills.online','futa'),'/menu?campus=futa');
 assert.equal(cmsDestination('//evil.test','https://holygrills.online'),'/menu');
});
test('CMS internal menu links preserve preview campus; other actions return to live',()=>{
 assert.equal(cmsDestination('/menu','https://holygrills.online','futa'),'/menu?campus=futa');
 assert.equal(cmsDestination('/register?ref=ABC','https://holygrills.online'),'https://holygrills.online/register?ref=ABC');
 assert.equal(previewPath('/menu','a & b'),'/menu?campus=a+%26+b');
});
test('only active hero placements become slides, including text-only slides',()=>{
 const banners=[{placement:'share',image_url:'https://res.cloudinary.com/a'},{is_active:false,metadata:{slides:[{display_mode:'text',title:'Hidden'}]}},{placement:'hero',metadata:{slides:[{display_mode:'text',title:'Visible',cta_url:'/menu'}]}}];
 assert.deepEqual(parseHeroes(banners,[]).map(s=>s.title),['Visible']);
});
test('legacy CMS image arrays and section fallback retain their copy',()=>{
 assert.equal(parseHeroes([{images:['https://res.cloudinary.com/a'],title:'Shared',action_label:'Order'}],[])[0].title,'Shared');
 assert.equal(parseHeroes([],[{section_type:'hero',content:{image_url:'https://res.cloudinary.com/a',headline:'Section',body:'Body'}}])[0].subtitle,'Body');
});
