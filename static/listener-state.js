/* Browser-local listening preferences. No account or server-side writes. */
(function(root, factory){
  const api=factory();
  if(typeof module==='object'&&module.exports)module.exports=api;
  else root.RewindListener=api;
})(typeof window==='undefined'?this:window,function(){
  'use strict';
  const KEY='rewind.listener.v1';
  const validId=id=>typeof id==='string'&&/^[a-f0-9]{32}$/.test(id);
  const ids=value=>Array.isArray(value)?[...new Set(value.filter(validId))].slice(0,10000):[];
  function normalize(value){
    const data=value&&typeof value==='object'&&value.version===1?value:{};
    const p=data.playback&&typeof data.playback==='object'?data.playback:{};
    return {version:1,favorites:ids(data.favorites),playback:{
      currentId:validId(p.currentId)?p.currentId:null,queue:ids(p.queue),
      position:Number.isFinite(p.position)&&p.position>=0?p.position:0,
      volume:Number.isFinite(p.volume)?Math.max(0,Math.min(1,p.volume)):.8,
      shuffle:p.shuffle===true,repeat:p.repeat===true
    }};
  }
  function create(storage, key=KEY){
    let state;
    try{state=normalize(JSON.parse(storage.getItem(key)));}catch{state=normalize(null);}
    const persist=()=>{try{storage.setItem(key,JSON.stringify(state));return true;}catch{return false;}};
    return {
      snapshot:()=>normalize(state),
      isFavorite:id=>state.favorites.includes(id),
      toggleFavorite(id){if(!validId(id))return false;state.favorites=state.favorites.includes(id)?state.favorites.filter(x=>x!==id):ids([...state.favorites,id]);return persist();},
      savePlayback(playback){state=normalize({...state,playback});return persist();},
      forget(id){state.favorites=state.favorites.filter(x=>x!==id);state.playback.queue=state.playback.queue.filter(x=>x!==id);if(state.playback.currentId===id){state.playback.currentId=null;state.playback.position=0;}return persist();},
      sync(raw){try{state=normalize(JSON.parse(raw));}catch{state=normalize(null);}},
    };
  }
  function restore(playback,available){
    const valid=new Set(available);
    const p=normalize({version:1,playback}).playback;
    p.queue=p.queue.filter(id=>valid.has(id));
    if(!valid.has(p.currentId)){p.currentId=null;p.position=0;}
    else if(!p.queue.includes(p.currentId))p.queue.unshift(p.currentId);
    return p;
  }
  function move(queue,index,direction){
    const next=queue.slice();const target=index+direction;
    if(!Number.isInteger(index)||![-1,1].includes(direction)||index<0||index>=next.length||target<0||target>=next.length)return next;
    [next[index],next[target]]=[next[target],next[index]];return next;
  }
  return {KEY,normalize,create,restore,move};
});
