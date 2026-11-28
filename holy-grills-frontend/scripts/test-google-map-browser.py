"""Controlled SDK contract; actual Google credentials/tiles need a live key."""
import os,signal,subprocess,tempfile,time,json
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
root=Path(__file__).resolve().parents[1]
html=root/'__maps-check.html';tsx=root/'__maps-check.tsx'
html.write_text('<div id="root"></div><script type="module" src="/__maps-check.tsx"></script>')
tsx.write_text('''import React,{useState} from 'react';import{createRoot}from'react-dom/client';import DeliveryLocationMap from './src/components/DeliveryLocationMap';
window.stats={maps:0,searches:0,fields:[]};
class Map{constructor(element,options){window.stats.mapOptions=options;window.stats.maps++;window.testMap=this;this.listeners={}}addListener(k,fn){this.listeners[k]=fn}panTo(){}setCenter(){}setZoom(){}}
class Marker{constructor(o){this.o=o;this.listeners={};window.markers.push(this)}addListener(k,fn){this.listeners[k]=fn}setPosition(){}setMap(){}}
window.markers=[];window.google={maps:{Map,Marker,event:{clearInstanceListeners(){}},importLibrary:async type=>type==='maps'?{Map}:{AutocompleteSessionToken:class{},AutocompleteSuggestion:{fetchAutocompleteSuggestions:async request=>{window.stats.searchRequest=request;window.stats.searches++;return{suggestions:[{placePrediction:{text:'Selected Nigerian address',toPlace:()=>({location:{lat:()=>7.3,lng:()=>5.2},fetchFields:async({fields})=>{window.stats.fields=fields}})}}]}}}}}};
navigator.geolocation.getCurrentPosition=(ok)=>ok({coords:{latitude:7.31,longitude:5.21}});
const gates=[{id:'west',name:'West Gate',lat:7.29,lng:5.14}];
function Harness(){const[pin,setPin]=useState({lat:7.295,lng:5.14}),[gate,setGate]=useState('');return <><DeliveryLocationMap savedAddressId="saved-home" pin={pin} onPinChange={setPin} gates={gates} onGateSelect={g=>setGate(g.id)}/><output aria-label="pin">{JSON.stringify(pin)}</output><output aria-label="gate">{gate}</output></>};createRoot(document.getElementById('root')).render(<Harness/>);
''')
log=Path(tempfile.mkdtemp())/'vite.log'
proc=subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1','--port','5247','--strictPort'],cwd=root,start_new_session=True,stdout=log.open('w'),stderr=subprocess.STDOUT)
try:
 time.sleep(2)
 with sync_playwright() as p:
  b=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);page=b.new_page(viewport={'width':393,'height':852})
  page.goto('http://127.0.0.1:5247/__maps-check.html')
  expect(page.get_by_text('Saved delivery pin selected',exact=True)).to_be_visible()
  assert page.evaluate('window.stats.maps')==0
  page.get_by_role('button',name='Change delivery pin',exact=True).click()
  page.wait_for_function('()=>window.testMap')
  page.evaluate('window.testMap.listeners.click({latLng:{lat:()=>7.32,lng:()=>5.22}})');expect(page.get_by_label('pin',exact=True)).to_contain_text('7.32')
  page.evaluate("window.markers.find(m=>m.o.draggable).listeners.dragend({latLng:{lat:()=>7.33,lng:()=>5.23}})");expect(page.get_by_label('pin',exact=True)).to_contain_text('7.33')
  page.get_by_role('button',name='Use my location').click();expect(page.get_by_label('pin',exact=True)).to_contain_text('7.31')
  page.evaluate("() => { navigator.geolocation.getCurrentPosition=(ok,fail,options)=>options.enableHighAccuracy?fail({code:3}):ok({coords:{latitude:7.34,longitude:5.24}}); }")
  page.get_by_role('button',name='Use my location').click();expect(page.get_by_label('pin',exact=True)).to_contain_text('7.34')
  page.evaluate("() => { navigator.geolocation.getCurrentPosition=(ok,fail)=>fail({code:1}); }")
  page.get_by_role('button',name='Use my location').click();expect(page.get_by_text('Location permission is blocked.',exact=False)).to_be_visible()
  page.get_by_label('Search delivery location').fill('FUTA address');page.get_by_role('button',name='Selected Nigerian address').click();expect(page.get_by_label('pin',exact=True)).to_contain_text('7.3')
  page.evaluate("window.markers.find(m=>m.o.title==='West Gate').listeners.click()");expect(page.get_by_label('gate',exact=True)).to_have_text('west')
  stats=page.evaluate('window.stats');assert stats['maps']==1 and stats['searches']==1 and stats['fields']==['location','formattedAddress'],stats
  assert stats['mapOptions']['minZoom']==11 and stats['mapOptions']['restriction']['strictBounds'] is True
  assert stats['searchRequest']['locationRestriction']['south']<7.295<stats['searchRequest']['locationRestriction']['north']
  b.close();print('PASS saved address creates zero map loads until explicit edit; local viewport/Places bounds; controlled Google SDK: map tap, draggable pin, GPS, Places search/selection, gate; pin changes create no extra map loads')
finally:
 os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=10);html.unlink(missing_ok=True);tsx.unlink(missing_ok=True)
