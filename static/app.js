'use strict';
const $ = (selector) => document.querySelector(selector);
const audio = $('#audio');
let token = $('meta[name="rewind-token"]').content;
let admin = document.body.dataset.admin === 'true';
let listenerAccount=null, accountMode="login", pendingSong=null;
let songs = [], decade = null, category = null, libraryError = null, favoritesOnly = false, currentId = null, queue = [], shuffle = false, repeat = false, editingId = null, uploadBusy = false, toastTimer;
let listenerStorage;
try{listenerStorage=window.localStorage;}catch{listenerStorage=null;}
let listenerKey=RewindListener.KEY+'.guest';
let listener=RewindListener.create(listenerStorage,listenerKey);
let personalRows={},personalReady=false,accountEpoch=0,historyOnly=false,playRecorded=false,lastAudioTime=0,listenedSeconds=0;
const favoriteBusy=new Set();
const personalSong=song=>({...song,favorite:listenerAccount?Boolean(personalRows[song.id]?.favorite):listener.isFavorite(song.id),play_count:listenerAccount?(personalRows[song.id]?.play_count||0):0});
function notifyAccount(){try{listenerStorage.setItem('rewind.auth.changed',String(Date.now()));}catch{}}
function activateAccount(account){
  const nextKey=RewindListener.KEY+'.'+(account?'user.'+account.id:admin?'admin':'guest');
  if(nextKey===listenerKey){listenerAccount=account;return;}
  audio.pause();saveListening();restored=false;accountEpoch++;currentId=null;pendingResume=null;queue=[];songs=[];personalRows={};personalReady=false;favoritesOnly=false;historyOnly=false;favoriteBusy.clear();
  audio.removeAttribute('src');audio.load();$('#resume-note').hidden=true;
  listenerAccount=account;listenerKey=nextKey;listener=RewindListener.create(listenerStorage,listenerKey);render();
}
function acceptPersonal(data){if(data.user_id!==listenerAccount?.id)return false;personalRows=Object.fromEntries(data.songs.map(row=>[row.song_id,row]));personalReady=true;return true;}
async function recordListening(){
  if(!listenerAccount||!currentId||playRecorded||!personalReady)return;
  playRecorded=true;const epoch=accountEpoch,id=currentId;
  try{const data=await api(`/api/me/library/${id}/played`,{method:'POST',body:'{}'});if(epoch===accountEpoch&&acceptPersonal(data)){songs=songs.map(personalSong);if(historyOnly)render();}}
  catch(error){if(epoch===accountEpoch)toast('Listening history could not be saved. '+error.message);}
}
let restored=false,pendingResume=null,lastSavedAt=0,storageNotice=false;
function persistNotice(ok){if(!ok&&!storageNotice){storageNotice=true;toast('This browser cannot save listening preferences. They will last only until this page closes.');}}
function saveListening(){
  if(!restored)return;
  persistNotice(listener.savePlayback({currentId,queue,position:pendingResume?.id===currentId?pendingResume.position:(Number.isFinite(audio.currentTime)?audio.currentTime:0),volume:audio.volume,shuffle,repeat}));
}
function restoreListening(){
  if(restored)return;restored=true;
  const saved=RewindListener.restore(listener.snapshot().playback,songs.map(s=>s.id));
  queue=saved.queue;shuffle=saved.shuffle;repeat=saved.repeat;audio.loop=repeat;audio.volume=saved.volume;
  $('#volume').value=saved.volume;$('#shuffle').setAttribute('aria-pressed',String(shuffle));$('#repeat').setAttribute('aria-pressed',String(repeat));
  if(saved.currentId){currentId=saved.currentId;pendingResume={id:currentId,position:saved.position};const song=songs.find(s=>s.id===currentId);if(!song.locked){audio.src=`/audio/${currentId}`;audio.load();}$('#resume-copy').textContent=`Continue ${song.title} from ${time(saved.position)}?`;$('#resume-note').hidden=false;$('#elapsed').textContent=time(saved.position);$('#duration').textContent=time(song.duration);}
  renderQueue();
}
const escapeHTML = (value) => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const time = seconds => { const safe = Number.isFinite(seconds) && seconds > 0 ? Math.floor(seconds) : 0; return `${Math.floor(safe / 60)}:${String(safe % 60).padStart(2, '0')}`; };
function toast(message) { clearTimeout(toastTimer); $('#toast').textContent = message; $('#toast').hidden = false; toastTimer = setTimeout(() => $('#toast').hidden = true, 5500); }
async function api(path, options = {}) {
  const response = await fetch(path, {...options, headers: {'X-Rewind-Token':token, ...(options.body instanceof FormData ? {} : {'Content-Type':'application/json'}), ...options.headers}});
  if (response.status === 204) return null;
  const data = await response.json().catch(() => ({error:'The server could not complete this request.'}));
  if (!response.ok) {if(response.status===401&&admin&&!path.startsWith('/api/admin/'))setAdmin(false);throw new Error(data.error || 'Something went wrong. Please try again.');}
  return data;
}
function visibleSongs() {
  const term = $('#search').value.trim().toLocaleLowerCase();
  const list = songs.filter(s => (!decade || s.decade === decade) && (!category || s.category === category) && (!favoritesOnly || s.favorite) && (!historyOnly || s.play_count>0) && [s.title,s.artist,s.album,s.category || '',String(s.year)].join(' ').toLocaleLowerCase().includes(term));
  const sort = $('#sort').value;
  if(historyOnly){list.sort((a,b)=>b.play_count-a.play_count||a.title.localeCompare(b.title));return list;}
  if (sort === 'title' || sort === 'artist') list.sort((a,b) => a[sort].localeCompare(b[sort]) || a.title.localeCompare(b.title));
  if (sort === 'year') list.sort((a,b) => a.year-b.year || a.title.localeCompare(b.title));
  return list;
}
function render() {
  const filtered = visibleSongs();
  $('#nav-count').textContent = songs.length;
  $('#favorite-count').textContent = songs.filter(s=>s.favorite).length;
  [1980,1990,2000].forEach(d => { const n = songs.filter(s=>s.decade===d).length; $(`#count-${d}`).textContent=`${n} ${n===1?'song':'songs'}`; $(`[data-decade="${d}"]`).setAttribute('aria-pressed', String(decade===d)); });
  $('#history-nav').hidden=!listenerAccount;$('#history-nav').classList.toggle('active',historyOnly);
  $('#all-library').classList.toggle('active',!favoritesOnly&&!historyOnly);
  $('#favorites-nav').classList.toggle('active',favoritesOnly);
  $('#all-library').toggleAttribute('aria-current',!favoritesOnly&&!historyOnly);
  $('#favorites-nav').toggleAttribute('aria-current',favoritesOnly);
  $('#history-nav').removeAttribute('aria-current');
  (historyOnly?$('#history-nav'):favoritesOnly ? $('#favorites-nav') : $('#all-library')).setAttribute('aria-current','page');
  for(const name of ['love','ghazal','travel','party']){const n=songs.filter(s=>s.category===name).length;$(`#category-count-${name}`).textContent=libraryError?'—':`${n} ${n===1?'song':'songs'}`;$(`[data-category="${name}"]`).setAttribute('aria-pressed',String(category===name));}
  $('#library-heading').textContent = (historyOnly?'Your most played':favoritesOnly?'Your favorites':'Your library') + (decade ? ` · ${decade}s` : '') + (category ? ` · ${category[0].toUpperCase()+category.slice(1)}` : '');
  const length = filtered.reduce((sum,s)=>sum+s.duration,0);
  $('#library-summary').textContent = `${filtered.length} ${filtered.length===1?'song':'songs'}${filtered.length?` · ${Math.ceil(length/60)} min of memories`:' · Room for your old favorites'}${favoritesOnly?(listenerAccount?' · Saved to your account':' · Saved on this browser'):historyOnly?' · Your listening history':''}`;
  $('#clear-filters').hidden = !(decade || category || favoritesOnly || historyOnly || $('#search').value);
  $('#play-all').disabled = !filtered.length;
  $('#library-content').setAttribute('aria-busy','false');
  if(libraryError){$('#library-summary').textContent='Library unavailable';$('#library-content').innerHTML=`<div class="empty-state"><div><h3>Couldn’t load your songs.</h3><p>${escapeHTML(admin?libraryError:'The music library is temporarily unavailable. Please try again later.')}</p></div><button class="button" id="retry-load">Try again</button></div>`;$('#retry-load').onclick=loadLibrary;return;}
  if (!filtered.length) {
    $('#library-content').innerHTML = `<div class="empty-state"><div class="empty-record" aria-hidden="true">${songs.length?'⌕':'↞'}</div><div><h3>${songs.length?(historyOnly?'Your listening history starts here.':favoritesOnly?'No favorites in this view.':'No songs in this view.'):(favoritesOnly?'No favorites yet.':'Your first track starts here.')}</h3><p>${songs.length?(historyOnly?'Listen to songs while signed in and your most-played tracks will appear here.':favoritesOnly?(listenerAccount?'Tap hearts to save favorites to your account.':'Tap the heart beside a song to save it on this browser. Clear filters to browse your collection.'):'Try another search, category or decade, or clear your filters to see the whole collection.'):(admin?'Bring your old favorites home. Add your own audio files and build a collection that sounds like you.':'Your collection is waiting for its first song. An admin can sign in to add music.')}</p></div><button class="button ${songs.length?'':'primary'}" id="empty-action">${songs.length?'Clear filters':(admin?'＋ Add your first song':'Admin login')}</button></div>`;
    $('#empty-action').onclick = songs.length ? clearFilters : showUpload;
  } else {
    $('#library-content').innerHTML = `<div class="track-header" aria-hidden="true"><span>#</span><span>Title / Artist</span><span class="track-album">Album</span><span>Year</span><span>Time</span><span></span></div>` + filtered.map((s,i)=>`<article class="track-row ${s.id===currentId?'current':''}" data-id="${s.id}" aria-label="${escapeHTML(s.title)} by ${escapeHTML(s.artist)}"><button class="icon-button track-play" data-action="play" aria-label="Play ${escapeHTML(s.title)}">${s.id===currentId&&!audio.paused?'Ⅱ':'▶'}</button><div class="track-title"><div class="track-art d${s.decade}" aria-hidden="true">${String(s.decade).slice(2)}s</div><div><strong title="${escapeHTML(s.title)}">${escapeHTML(s.title)}</strong><small>${escapeHTML(s.artist)}${historyOnly?` · ${s.play_count} ${s.play_count===1?'play':'plays'}`:s.locked?' · Sign in to listen':s.preview?' · Free preview':''}</small></div></div><span class="track-album" title="${escapeHTML(s.album)}">${escapeHTML(s.album)||'—'}</span><span class="track-year">${s.year}</span><span class="track-duration">${time(s.duration)}</span><div class="track-actions"><button class="icon-button" data-action="favorite" aria-label="${s.favorite?'Unfavorite':'Favorite'} ${escapeHTML(s.title)}" aria-pressed="${s.favorite}">${s.favorite?'♥':'♡'}</button><button class="icon-button" data-action="queue" aria-label="Add ${escapeHTML(s.title)} to queue" ${queue.includes(s.id)?'disabled':''}>＋</button>${admin?`<button class="icon-button edit-track" data-action="edit" aria-label="Edit ${escapeHTML(s.title)}">···</button>`:''}</div></article>`).join('');
  }
  updateNowPlaying();
  renderQueue();
}
function clearFilters() { decade=null; category=null; favoritesOnly=false;historyOnly=false; $('#search').value=''; render(); }
function showUpload() { if(!admin){showLogin();return;} $('#upload-panel').hidden=false; $('#upload-panel').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'start'}); $('#audio-files').focus({preventScroll:true}); }
async function loadLibrary() {
  const epoch=accountEpoch;
  try {
    const rows=await api('/api/songs');
    if(epoch!==accountEpoch)return;
    if(listenerAccount){const personal=await api('/api/me/library');if(epoch!==accountEpoch)return;if(!acceptPersonal(personal))throw new Error('Your session changed. Refresh to load your account.');}
    songs=rows.map(personalSong);libraryError=null;restoreListening();render();
  }catch(error){if(epoch===accountEpoch){personalReady=false;personalRows={};songs=songs.map(personalSong);libraryError=error.message;render();}}
}
function updateNowPlaying() {
  const s = songs.find(s=>s.id===currentId);
  $('#now-title').textContent = s?.title || 'Ready when you are';
  $('#now-artist').textContent = s ? `${s.artist} · ${s.year}` : 'Add a song to start listening';
  $('#player-art').textContent = s ? `${String(s.decade).slice(2)}s` : '↞';
  for(const id of ['play-pause','previous','next','player-favorite']) $(`#${id}`).disabled=!s;
  $('#seek').disabled = !s || !Number.isFinite(audio.duration);
  $('#player-favorite').textContent = s?.favorite?'♥':'♡';
  $('#player-favorite').setAttribute('aria-pressed',String(Boolean(s?.favorite)));
  syncPlayback();
}
function syncPlayback() {
  const playing= !audio.paused&&!audio.ended;
  document.body.classList.toggle('is-playing',playing);
  $('#play-pause').textContent=playing?'Ⅱ':'▶';
  $('#play-pause').setAttribute('aria-label',playing?'Pause':'Play');
  document.querySelectorAll('.track-row').forEach(row => { const active = row.dataset.id===currentId; row.classList.toggle('current',active); const button = row.querySelector('.track-play'); button.textContent=active&&playing?'Ⅱ':'▶'; const s=songs.find(s=>s.id===row.dataset.id); button.setAttribute('aria-label',`${active&&playing?'Pause':'Play'} ${s.title}`); });
}
async function playSong(id, newQueue=false) {
  const s=songs.find(s=>s.id===id); if(!s)return;if(s.locked){pendingSong=id;showAccount();return;}
  if(newQueue) queue=visibleSongs().map(s=>s.id);
  $('#resume-note').hidden=true;
  if(!queue.includes(id))queue=[id];
  if(currentId!==id || !audio.getAttribute('src')) {playRecorded=false;listenedSeconds=0;lastAudioTime=0; if(currentId!==id)pendingResume=null; currentId=id; audio.src=`/audio/${id}`; $('#elapsed').textContent='0:00'; $('#duration').textContent=time(s.duration); $('#seek').value=0; }
  updateNowPlaying();renderQueue();saveListening();
  try { await audio.play(); } catch(error) { if(error.name!=='AbortError') toast('This browser could not play that file. Try an MP3 or WAV version.'); }
  syncPlayback();
}
function step(direction, ended=false) {
  queue=queue.filter(id=>songs.some(s=>s.id===id));
  if(!queue.length)return;
  if(direction===-1&&audio.currentTime>3){audio.currentTime=0;return;}
  let index=queue.indexOf(currentId)+direction;
  if(shuffle&&queue.length>1){const choices=queue.filter(id=>id!==currentId);playSong(choices[Math.floor(Math.random()*choices.length)]);return;}
  if(ended&&index>=queue.length){audio.pause();audio.currentTime=0;syncPlayback();return;}
  playSong(queue[(index+queue.length)%queue.length]);
}
async function favorite(id) {
  const song=songs.find(s=>s.id===id);if(!song)return;
  if(!listenerAccount){persistNotice(listener.toggleFavorite(id));songs=songs.map(personalSong);render();return;}
  if(!personalReady||favoriteBusy.has(id))return;
  const epoch=accountEpoch;favoriteBusy.add(id);
  try{const data=await api(`/api/me/library/${id}/favorite`,{method:'POST',body:JSON.stringify({favorite:!song.favorite})});if(epoch===accountEpoch&&acceptPersonal(data)){songs=songs.map(personalSong);render();}}
  catch(error){if(epoch===accountEpoch)toast('Favorite could not be saved. '+error.message);}
  finally{if(epoch===accountEpoch)favoriteBusy.delete(id);}
}
function renderQueue(){
  queue=queue.filter(id=>songs.some(s=>s.id===id));
  const current=queue.indexOf(currentId);
  $('#queue-count').textContent=Math.max(0,queue.length-current-1);
  $('#queue-help').textContent=shuffle?'Shuffle is on. Reordering switches to your chosen order.':'Your listening order. Move upcoming songs with the arrows.';
  $('#clear-queue').disabled=queue.length<=current+1;
  $('#queue-list').innerHTML=queue.length?queue.map((id,index)=>{
    const song=songs.find(s=>s.id===id);const upcoming=index>current;
    return `<li data-index="${index}" class="queue-item ${id===currentId?'current':''}"><button class="queue-title" data-queue-action="play" aria-label="Play queued ${escapeHTML(song.title)}"><strong>${escapeHTML(song.title)}</strong><small>${id===currentId?'Current song':index<current?'Earlier':'Up next'} · ${escapeHTML(song.artist)}</small></button><div class="queue-actions"><button class="icon-button" data-queue-action="up" aria-label="Move ${escapeHTML(song.title)} earlier" ${!upcoming||index===current+1?'disabled':''}>↑</button><button class="icon-button" data-queue-action="down" aria-label="Move ${escapeHTML(song.title)} later" ${!upcoming||index===queue.length-1?'disabled':''}>↓</button><button class="icon-button" data-queue-action="remove" aria-label="Remove ${escapeHTML(song.title)} from queue" ${id===currentId?'disabled':''}>×</button></div></li>`;
  }).join(''):'<li class="queue-empty">Your queue is empty. Play a collection or use the ＋ beside a song to add it here.</li>';
}
function addToQueue(id){if(!queue.includes(id)){queue.push(id);saveListening();render();toast('Added to Up next.');}}
$('#open-queue').onclick=()=>{renderQueue();$('#queue-dialog').showModal();};
$('#close-queue').onclick=()=>$('#queue-dialog').close();
$('#queue-list').onclick=event=>{const button=event.target.closest('[data-queue-action]');if(!button)return;const index=Number(button.closest('[data-index]').dataset.index);const id=queue[index];if(!id)return;const action=button.dataset.queueAction;if(action==='play'){playSong(id);return;}if(action==='remove'){if(id!==currentId)queue.splice(index,1);}else{const direction=action==='up'?-1:1;const current=queue.indexOf(currentId);if(index<=current||index+direction<=current)return;queue=RewindListener.move(queue,index,direction);shuffle=false;$('#shuffle').setAttribute('aria-pressed','false');}saveListening();render();const replacement=$('#queue-list').querySelector(`[data-index="${Math.min(index,queue.length-1)}"] button:not(:disabled)`);if(replacement)replacement.focus();};
$('#clear-queue').onclick=()=>{const current=queue.indexOf(currentId);queue=current>=0?queue.slice(0,current+1):[];saveListening();render();};
$('#resume-listening').onclick=()=>playSong(currentId);
window.addEventListener('pagehide',saveListening);
document.addEventListener('visibilitychange',()=>{if(document.hidden)saveListening();});
window.addEventListener('storage',event=>{if(event.key==='rewind.auth.changed'){activateAccount(null);loadAccount().then(loadLibrary);}else if(event.key===listenerKey){listener.sync(event.newValue);songs=songs.map(personalSong);render();}});
$('#library-content').addEventListener('click',event=>{const button=event.target.closest('[data-action]');if(!button)return;const id=button.closest('.track-row').dataset.id;if(button.dataset.action==='play'){if(currentId===id&&!audio.paused)audio.pause();else playSong(id,true);}if(button.dataset.action==='queue')addToQueue(id);if(button.dataset.action==='favorite')favorite(id);if(button.dataset.action==='edit')editSong(id);});
$('#all-library').onclick=clearFilters;
$('#history-nav').onclick=()=>{historyOnly=true;favoritesOnly=false;decade=null;category=null;$('#search').value='';render();};
$('#favorites-nav').onclick=()=>{historyOnly=false;favoritesOnly=true;decade=null;category=null;render();};
for(const id of ['add-music','upload-nav']) $(`#${id}`).onclick=showUpload;
$('#close-upload').onclick=()=>{if(!uploadBusy){$('#upload-panel').hidden=true;$('#add-music').focus();}else toast('Please wait for your upload to finish.');};
for(const button of document.querySelectorAll('[data-decade]'))button.onclick=()=>{decade=decade===Number(button.dataset.decade)?null:Number(button.dataset.decade);render();};
for(const button of document.querySelectorAll('[data-category]'))button.onclick=()=>{category=category===button.dataset.category?null:button.dataset.category;render();};
$('#search').oninput=render;$('#sort').onchange=render;$('#clear-filters').onclick=clearFilters;
$('#play-all').onclick=()=>{const list=visibleSongs();const first=list.find(s=>!s.locked)||list[0];if(first)playSong(first.id,true);};
$('#play-pause').onclick=()=>{if(!currentId)return;if(audio.paused)playSong(currentId);else audio.pause();};
$('#previous').onclick=()=>step(-1);$('#next').onclick=()=>step(1);
$('#shuffle').onclick=()=>{shuffle=!shuffle;$('#shuffle').setAttribute('aria-pressed',String(shuffle));renderQueue();saveListening();toast(`Shuffle ${shuffle?'on':'off'}`);};
$('#repeat').onclick=()=>{repeat=!repeat;audio.loop=repeat;$('#repeat').setAttribute('aria-pressed',String(repeat));saveListening();toast(`Repeat song ${repeat?'on':'off'}`);};
$('#player-favorite').onclick=()=>favorite(currentId);
audio.volume=listener.snapshot().playback.volume;
$('#volume').oninput=()=>{audio.volume=Number($('#volume').value);audio.muted=false;$('#mute').setAttribute('aria-pressed','false');$('#mute').setAttribute('aria-label','Mute');saveListening();};
$('#mute').onclick=()=>{audio.muted=!audio.muted;$('#mute').setAttribute('aria-pressed',String(audio.muted));$('#mute').setAttribute('aria-label',audio.muted?'Unmute':'Mute');};
$('#seek').oninput=()=>{if(Number.isFinite(audio.duration))audio.currentTime=Number($('#seek').value)/100*audio.duration;saveListening();};
audio.addEventListener('loadedmetadata',()=>{if(pendingResume?.id===currentId&&Number.isFinite(audio.duration)){audio.currentTime=Math.min(pendingResume.position,Math.max(0,audio.duration-.1));pendingResume=null;}$('#duration').textContent=time(audio.duration);$('#seek').disabled=!Number.isFinite(audio.duration);});
audio.addEventListener('timeupdate',()=>{const delta=audio.currentTime-lastAudioTime;if(audio.loop&&delta< -1&&lastAudioTime>audio.duration-2){playRecorded=false;listenedSeconds=0;}if(!audio.paused&&delta>0&&delta<2){listenedSeconds+=delta;if(listenedSeconds>=Math.min(10,audio.duration/2))recordListening();}lastAudioTime=audio.currentTime;if(Date.now()-lastSavedAt>2000){lastSavedAt=Date.now();saveListening();}$('#elapsed').textContent=time(audio.currentTime);$('#seek').value=Number.isFinite(audio.duration)&&audio.duration>0?audio.currentTime/audio.duration*100:0;});
audio.addEventListener('seeking',()=>{lastAudioTime=audio.currentTime;});
audio.addEventListener('play',()=>{$('#resume-note').hidden=true;syncPlayback();});audio.addEventListener('pause',()=>{syncPlayback();saveListening();});audio.addEventListener('ended',()=>step(1,true));
audio.addEventListener('error',()=>{if(currentId)toast('Unable to play this audio. The file may be missing or use a codec your browser does not support.');syncPlayback();});
document.addEventListener('keydown',event=>{if(event.code==='Space'&&event.target===document.body&&currentId){event.preventDefault();$('#play-pause').click();}});
function editSong(id){if(!admin){showLogin();return;}const s=songs.find(s=>s.id===id);if(!s)return;editingId=id;for(const key of ['title','artist','album','year','category'])$('#edit-form').elements[key].value=s[key];$('#edit-error').textContent='';$('#edit-dialog').showModal();}
$('#close-edit').onclick=()=>$('#edit-dialog').close();
$('#edit-form').onsubmit=async event=>{event.preventDefault();const submit=event.submitter;submit.disabled=true;try { const data=Object.fromEntries(new FormData(event.target));data.year=Number(data.year);const updated=await api(`/api/songs/${editingId}`,{method:'PATCH',body:JSON.stringify(data)});songs=songs.map(s=>s.id===editingId?personalSong(updated):s);$('#edit-dialog').close();render();toast('Song details saved.'); }catch(error){$('#edit-error').textContent=error.message;}finally{submit.disabled=false;}};
$('#delete-song').onclick=()=>{$('#delete-copy').textContent=songs.find(s=>s.id===editingId)?.title||'';$('#delete-dialog').showModal();};
$('#cancel-delete').onclick=()=>$('#delete-dialog').close();
$('#confirm-delete').onclick=async()=>{const button=$('#confirm-delete');button.disabled=true;try{await api(`/api/songs/${editingId}`,{method:'DELETE'});if(currentId===editingId){audio.pause();audio.removeAttribute('src');audio.load();currentId=null;pendingResume=null;$('#resume-note').hidden=true;$('#seek').value=0;$('#elapsed').textContent='0:00';$('#duration').textContent='0:00';}persistNotice(listener.forget(editingId));songs=songs.filter(s=>s.id!==editingId);queue=queue.filter(id=>id!==editingId);$('#delete-dialog').close();$('#edit-dialog').close();saveListening();render();toast('Song removed from your library.');}catch(error){toast(error.message);}finally{button.disabled=false;}};
const drop=$('#drop-zone');
let selectedFiles=[];
for(const eventName of ['dragenter','dragover'])drop.addEventListener(eventName,event=>{event.preventDefault();if(!uploadBusy)drop.classList.add('dragging');});
for(const eventName of ['dragleave','drop'])drop.addEventListener(eventName,()=>drop.classList.remove('dragging'));
$('#audio-files').addEventListener('change',event=>{if(!uploadBusy)selectedFiles.push(...Array.from(event.target.files).filter(file=>!selectedFiles.some(selected=>selected.name===file.name&&selected.size===file.size&&selected.lastModified===file.lastModified)));});
drop.addEventListener('drop',event=>{event.preventDefault();if(!uploadBusy&&event.dataTransfer.files.length){selectedFiles.push(...Array.from(event.dataTransfer.files).filter(file=>!selectedFiles.some(selected=>selected.name===file.name&&selected.size===file.size&&selected.lastModified===file.lastModified)));}});
function sendFile(file,year,category,onProgress){return new Promise((resolve,reject)=>{const xhr=new XMLHttpRequest();xhr.open('POST','/api/songs');xhr.setRequestHeader('X-Rewind-Token',token);xhr.responseType='json';xhr.timeout=30*60*1000;xhr.upload.onprogress=event=>{if(event.lengthComputable)onProgress(event.loaded/event.total);};xhr.onload=()=>xhr.status>=200&&xhr.status<300?resolve(xhr.response):reject(new Error(xhr.response?.error||'Upload failed. Please try again.'));xhr.onerror=()=>reject(new Error('Connection lost. Check the server and retry.'));xhr.ontimeout=()=>reject(new Error('Upload timed out. Check the library before trying again.'));const form=new FormData();form.append('file',file);form.append('year',year);form.append('category',category);xhr.send(form);});}
$('#upload-form').onsubmit=async event=>{
  event.preventDefault();if(uploadBusy)return;
  const files=[...selectedFiles];if(!files.length)return;
  const year=$('#upload-year').value;const batchCategory=$('#upload-category').value;$('#upload-category').disabled=true;uploadBusy=true;$('#upload-submit').disabled=true;$('#audio-files').disabled=true;$('#upload-year').disabled=true;$('#upload-progress').hidden=false;
  const errors=[];let count=0;
  for(let i=0;i<files.length;i++){
    const file=files[i];$('#upload-status').textContent=`Adding ${i+1} of ${files.length}: ${file.name}`;
    try{if(file.size>200*1024*1024)throw new Error('File exceeds 200 MB.');const song=await sendFile(file,year,batchCategory,fraction=>$('#upload-progress').value=(i+fraction)/files.length*100);songs.unshift(personalSong(song));count++;render();}
    catch(error){errors.push(`${file.name}: ${error.message}`);}
  }
  $('#upload-progress').value=100;$('#upload-status').textContent=`${count} ${count===1?'song':'songs'} added.${errors.length?'\n'+errors.join('\n'): ' Your collection is ready to play.'}`;
  selectedFiles=[];$('#audio-files').value='';uploadBusy=false;$('#upload-submit').disabled=false;$('#audio-files').disabled=false;$('#upload-year').disabled=false;$('#upload-category').disabled=false;
  if(count)toast(`${count} ${count===1?'song':'songs'} added to your library.`);
};
function showAccount(){accountMode='login';updateAccountForm();$('#account-error').textContent='';$('#account-dialog').showModal();}
function updateAccountForm(){const registering=accountMode==='register';$('#account-heading').textContent=registering?'Create your listener account':'Listen to the whole collection';$('#account-submit').textContent=registering?'Create account':'Sign in';$('#account-switch').textContent=registering?'I already have an account':'Create an account';$('#account-form').elements.password.autocomplete=registering?'new-password':'current-password';}
function updateAccountButton(){const button=$('#listener-access');button.hidden=admin;button.textContent=listenerAccount?`Sign out (${listenerAccount.username})`:'Listener sign in';}
async function loadAccount(){try{const status=await api('/api/account');token=status.csrf;admin=status.admin;activateAccount(status.listener);document.body.dataset.admin=String(admin);$('#add-music').hidden=!admin;$('#upload-nav').hidden=!admin;$('#admin-access').textContent=admin?'Sign out':'Admin login';if(!admin){$('#upload-panel').hidden=true;$('#edit-dialog').close();$('#delete-dialog').close();}updateAccountButton();}catch{updateAccountButton();}}
$('#close-account').onclick=()=>$('#account-dialog').close();
$('#account-dialog').addEventListener('close',()=>{$('#account-form').elements.password.value='';});
$('#account-switch').onclick=()=>{accountMode=accountMode==='login'?'register':'login';$('#account-error').textContent='';updateAccountForm();};
$('#listener-access').onclick=async()=>{if(!listenerAccount){showAccount();return;}try{const result=await api('/api/account/logout',{method:'POST',body:'{}'});token=result.csrf;activateAccount(null);notifyAccount();audio.pause();audio.removeAttribute('src');audio.load();currentId=null;pendingResume=null;$('#resume-note').hidden=true;updateAccountButton();await loadLibrary();saveListening();toast('Signed out. The free preview is still available.');}catch(error){toast(error.message);}};
$('#account-form').onsubmit=async event=>{event.preventDefault();const button=$('#account-submit');button.disabled=true;$('#account-switch').disabled=true;try{const result=await api(`/api/account/${accountMode}`,{method:'POST',body:JSON.stringify(Object.fromEntries(new FormData(event.target)))});token=result.csrf;activateAccount(result.listener);notifyAccount();updateAccountButton();$('#account-dialog').close();await loadLibrary();toast('Signed in. The whole collection is ready.');if(pendingSong){const id=pendingSong;pendingSong=null;playSong(id,true);}else if(pendingResume&&currentId){audio.src=`/audio/${currentId}`;audio.load();}}catch(error){$('#account-error').textContent=error.message;}finally{button.disabled=false;$('#account-switch').disabled=false;}};
function showLogin(){ $('#login-error').textContent=''; $('#login-dialog').showModal(); }
function setAdmin(value){admin=value;activateAccount(null);notifyAccount();updateAccountButton();document.body.dataset.admin=String(value);$('#add-music').hidden=!value;$('#upload-nav').hidden=!value;$('#admin-access').textContent=value?'Sign out':'Admin login';if(!value){if(libraryError)libraryError='The music library is temporarily unavailable. Please try again later.';$('#upload-panel').hidden=true;$('#edit-dialog').close();$('#delete-dialog').close();}render();}
$('#admin-access').onclick=async()=>{if(!admin){showLogin();return;}if(uploadBusy){toast('Wait for your upload to finish before signing out.');return;}try{const result=await api('/api/admin/logout',{method:'POST',body:'{}'});token=result.csrf;audio.pause();audio.removeAttribute('src');audio.load();currentId=null;pendingResume=null;$('#resume-note').hidden=true;setAdmin(false);await loadLibrary();saveListening();toast('Signed out.');}catch(error){toast(error.message);}};
$('#close-login').onclick=()=>$('#login-dialog').close();
$('#login-dialog').addEventListener('close',()=>{$('#login-form').elements.password.value='';});
$('#login-form').onsubmit=async event=>{event.preventDefault();const button=event.submitter;button.disabled=true;try{const result=await api('/api/admin/login',{method:'POST',body:JSON.stringify(Object.fromEntries(new FormData(event.target)))});token=result.csrf;setAdmin(true);loadLibrary();$('#login-dialog').close();toast('Signed in as admin. You can now add music.');}catch(error){$('#login-error').textContent=error.message;}finally{button.disabled=false;}};
loadAccount().then(loadLibrary);
