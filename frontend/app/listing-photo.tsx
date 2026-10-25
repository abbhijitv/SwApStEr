'use client';
import Image from 'next/image';
import {useState} from 'react';
import {BookOpen, Calculator, Cpu, House, Package, Ruler} from 'lucide-react';

type PhotoItem={id:number;title:string;category:string;icon?:string;housing?:{listing_type:string}|null};
type Group='ti84'|'nspire'|'books'|'electronics'|'drafting'|'apartment'|'private-room'|'room-rental'|'other';
const pools:Record<Exclude<Group,'other'>,string[]>={
 ti84:['calculator-ti84','calculator-ti84-red'],
 nspire:['calculator-nspire','calculator-nspire-cx'],
 books:['books-study','books-open'],
 electronics:['electronics-breadboard','electronics-sensors'],
 drafting:['drafting-tools','drafting-compass'],
 apartment:['housing-living','housing-kitchen'],
 'private-room':['housing-bedroom','housing-bedroom-desk'],
 'room-rental':['housing-room','housing-room-simple'],
};
const descriptions:Record<Group,string>={ti84:'TI-84 Plus CE graphing calculator',nspire:'TI-Nspire graphing calculator',books:'Textbooks and study notes at a desk',electronics:'Arduino board, breadboard and electronics components',drafting:'Engineering drawing instruments',apartment:'Apartment interior', 'private-room':'Furnished private bedroom','room-rental':'Bedroom with living or study space',other:'Campus listing'};
function groupFor(item:PhotoItem):Group{
 if(item.housing)return item.housing.listing_type==='Apartment sublease'?'apartment':item.housing.listing_type==='Private room sublease'?'private-room':'room-rental';
 if(item.category==='Calculators')return /nspire/i.test(item.title)?'nspire':'ti84';
 if(item.category==='Textbooks')return 'books';
 if(item.category==='Lab kits')return 'electronics';
 if(item.category==='Drafting')return 'drafting';
 return 'other';
}
export function listingPhoto(item:PhotoItem){
 const group=groupFor(item);
 if(group==='other')return {group,src:null,alt:descriptions[group]};
 const pool=pools[group];
 // Persisted IDs keep a listing's illustrative photo stable across refreshes and sorting.
 const index=Math.abs(item.id)%pool.length;
 return {group,src:`/images/marketplace/${pool[index]}.webp`,alt:`Illustrative photo: ${descriptions[group]}`};
}
export function ListingPhoto({item,small=false,detail=false}:{item:PhotoItem;small?:boolean;detail?:boolean}){
 const photo=listingPhoto(item);
 const [failedSource,setFailedSource]=useState<string|null>(null);
 const [loadedSource,setLoadedSource]=useState<string|null>(null);
 const available=photo.src!==null&&failedSource!==photo.src;
 const Icon=photo.group==='ti84'||photo.group==='nspire'?Calculator:photo.group==='books'?BookOpen:photo.group==='electronics'?Cpu:photo.group==='drafting'?Ruler:item.housing?House:Package;
 return <div className={`item-art listing-photo ${small?'small':''} ${loadedSource===photo.src?'photo-loaded':''}`} data-photo-group={photo.group}>
  {available?<><Image key={photo.src} src={photo.src!} alt={photo.alt} fill sizes={detail?'(max-width: 760px) calc(100vw - 24px), 720px':small?'(max-width: 760px) 75px, 190px':'(max-width: 760px) 50vw, (max-width: 1100px) 33vw, 500px'} loading="lazy" quality={75} onLoad={()=>setLoadedSource(photo.src)} onError={()=>setFailedSource(photo.src)}/><a className="illustrative-label" href={`/images/marketplace/credits.html#${photo.src!.split('/').pop()}`} target="_blank" rel="noopener noreferrer" aria-label="Illustrative photo — source and license">Illustrative photo</a></>:<div className="photo-fallback"><Icon size={small?26:44} strokeWidth={1.4}/>{!small&&<span>{item.housing?'Housing photo unavailable':`${item.category==='Other'?'Listing':item.category} photo unavailable`}</span>}</div>}
 </div>;
}
