const test=require('node:test');
const assert=require('node:assert/strict');
const L=require('../static/listener-state.js');
const a='a'.repeat(32),b='b'.repeat(32),c='c'.repeat(32);
const storage=()=>{let data=null;return {getItem:()=>data,setItem:(key,value)=>{data=value;}}};
test('favorites survive reload and remain isolated between browser stores',()=>{
 const first=storage(),second=storage();const state=L.create(first);
 assert.equal(state.toggleFavorite(a),true);
 assert.equal(L.create(first).isFavorite(a),true);
 assert.equal(L.create(second).isFavorite(a),false);
 state.toggleFavorite(a);assert.equal(L.create(first).isFavorite(a),false);
});
test('playback position queue and controls survive reload',()=>{
 const disk=storage();L.create(disk).savePlayback({currentId:b,queue:[a,b,c],position:12.5,volume:.3,shuffle:true,repeat:true});
 assert.deepEqual(L.create(disk).snapshot().playback,{currentId:b,queue:[a,b,c],position:12.5,volume:.3,shuffle:true,repeat:true});
});
test('corrupt or blocked storage falls back without breaking listening',()=>{
 const broken={getItem:()=>'{bad',setItem:()=>{throw Error('blocked')}};
 const state=L.create(broken);assert.equal(state.isFavorite(a),false);
 assert.equal(state.toggleFavorite(a),false);assert.equal(state.isFavorite(a),true);
 assert.equal(L.create(null).savePlayback({}),false);
});
test('invalid saved data is normalized',()=>{
 const state=L.normalize({version:1,favorites:[a,a,'bad'],playback:{currentId:'bad',queue:[b,b,null],position:-5,volume:5,shuffle:'true'}});
 assert.deepEqual(state.favorites,[a]);assert.deepEqual(state.playback.queue,[b]);
 assert.equal(state.playback.currentId,null);assert.equal(state.playback.position,0);assert.equal(state.playback.volume,1);assert.equal(state.playback.shuffle,false);
});
test('missing songs are removed from restored queue and resume',()=>{
 assert.deepEqual(L.restore({currentId:b,queue:[a,b,c],position:10},[a,c]).queue,[a,c]);
 assert.equal(L.restore({currentId:b,position:10},[a]).position,0);
 assert.deepEqual(L.restore({currentId:a,queue:[b]},[a,b]).queue,[a,b]);
});
test('queue movement respects boundaries and leaves original unchanged',()=>{
 const queue=[a,b,c];assert.deepEqual(L.move(queue,2,-1),[a,c,b]);
 assert.deepEqual(queue,[a,b,c]);assert.deepEqual(L.move(queue,0,-1),queue);
 assert.deepEqual(L.move(queue,2,1),queue);
});
test('forgetting deleted song clears its resume and favorite',()=>{
 const state=L.create(storage());state.toggleFavorite(a);state.savePlayback({currentId:a,queue:[a,b],position:10});state.forget(a);
 assert.equal(state.isFavorite(a),false);assert.equal(state.snapshot().playback.currentId,null);assert.deepEqual(state.snapshot().playback.queue,[b]);
});
test('account-scoped playback never reads another account or guest state',()=>{
 const data=new Map();const disk={getItem:key=>data.get(key),setItem:(key,value)=>data.set(key,value)};
 L.create(disk,L.KEY+'.user.alice').savePlayback({currentId:a,queue:[a,b],position:15});
 assert.equal(L.create(disk,L.KEY+'.user.bob').snapshot().playback.currentId,null);
 assert.equal(L.create(disk,L.KEY+'.guest').snapshot().playback.currentId,null);
 assert.equal(L.create(disk,L.KEY+'.user.alice').snapshot().playback.position,15);
});
