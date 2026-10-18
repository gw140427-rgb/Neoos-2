const $=id=>document.getElementById(id);
const video=$('video');
let clips=[],selectedClipId=null,clipSeq=0,musicUrl=null,musicFile=null,musicEl=null,audioContext=null,videoAudioNode=null,musicAudioNode=null,mixDestination=null,sourceUrl=null,sourceFile=null;
const fmt=s=>{if(!Number.isFinite(s)||s<0)s=0;return String(Math.floor(s/60)).padStart(2,'0')+':'+String(Math.floor(s%60)).padStart(2,'0')};
const selectedClip=()=>clips.find(c=>c.id===selectedClipId)||null;
function updateTime(){
 $('timeLabel').textContent=fmt(video.currentTime)+' / '+fmt(video.duration);
 const c=selectedClip(),idx=clips.findIndex(x=>x.id===selectedClipId);
 const pct=clips.length?((Math.max(0,idx)+((video.duration?video.currentTime/video.duration:0)))/clips.length)*100:0;
 $('timelineFill').style.width=pct+'%';
}
function updateCaption(){const el=$('captionPreview');el.textContent=$('captionText').value;el.style.color=$('captionColor').value;el.style.fontSize=$('captionSize').value+'px';}
function initAudio(){
 if(audioContext)return;
 const AC=window.AudioContext||window.webkitAudioContext;
 if(!AC)throw Error('이 브라우저는 오디오 믹싱을 지원하지 않습니다.');
 audioContext=new AC();mixDestination=audioContext.createMediaStreamDestination();
 videoAudioNode=audioContext.createMediaElementSource(video);
 videoAudioNode.connect(audioContext.destination);videoAudioNode.connect(mixDestination);
 if(musicEl){musicAudioNode=audioContext.createMediaElementSource(musicEl);musicAudioNode.connect(audioContext.destination);musicAudioNode.connect(mixDestination);}
}
function setMusicVolume(){if(musicEl)musicEl.volume=Number($('musicVolume').value);}
function renderClips(){
 const list=$('clipList');list.replaceChildren();
 if(!clips.length){const empty=document.createElement('div');empty.className='clip-empty';empty.textContent='아직 영상이 없습니다';list.append(empty);$('clipName').textContent='아직 영상이 없습니다';$('exportBtn').disabled=true;return;}
 clips.forEach((c,i)=>{
  const row=document.createElement('div');row.className='clip-row'+(c.id===selectedClipId?' selected':'');
  const pick=document.createElement('button');pick.className='clip-pick';pick.textContent=(i+1)+'. '+c.file.name;pick.title=c.file.name;pick.onclick=()=>selectClip(c.id);
  const up=document.createElement('button');up.className='clip-order';up.textContent='▲';up.title='위로 이동';up.disabled=i===0;up.onclick=()=>moveClip(i,-1);
  const down=document.createElement('button');down.className='clip-order';down.textContent='▼';down.title='아래로 이동';down.disabled=i===clips.length-1;down.onclick=()=>moveClip(i,1);
  const del=document.createElement('button');del.className='clip-order clip-delete';del.textContent='×';del.title='클립 삭제';del.onclick=()=>removeClip(c.id);
  row.append(pick,up,down,del);list.append(row);
 });
 const c=selectedClip();$('clipName').textContent=c?'선택됨: '+c.file.name+' · '+fmt(c.end-c.start):'클립을 선택하세요';$('exportBtn').disabled=!clips.length;
}
async function waitMetadata(){if(video.readyState>=1&&Number.isFinite(video.duration))return;await new Promise((resolve,reject)=>{video.addEventListener('loadedmetadata',resolve,{once:true});video.addEventListener('error',()=>reject(Error('영상 파일을 읽지 못했습니다.')),{once:true});});}
async function selectClip(id){
 const c=clips.find(x=>x.id===id);if(!c)return;
 video.pause();selectedClipId=id;sourceUrl=c.url;sourceFile=c.file;
 if(video.src!==c.url){video.src=c.url;video.load();await waitMetadata();}
 video.hidden=false;$('empty').hidden=true;
 $('trimStart').value=c.start;$('trimEnd').value=c.end;
 renderClips();updateTime();
}
function moveClip(i,delta){const j=i+delta;if(j<0||j>=clips.length)return;[clips[i],clips[j]]=[clips[j],clips[i]];renderClips();}
function removeClip(id){const i=clips.findIndex(c=>c.id===id);if(i<0)return;const c=clips[i];if(c.url)URL.revokeObjectURL(c.url);clips.splice(i,1);if(selectedClipId===id){selectedClipId=null;if(clips.length)selectClip(clips[Math.min(i,clips.length-1)].id);else{video.pause();video.removeAttribute('src');video.load();video.hidden=true;$('empty').hidden=false;sourceUrl=null;sourceFile=null;}}renderClips();}
$('importBtn').onclick=()=>$('fileInput').click();
$('fileInput').onchange=async()=>{
 const files=Array.from($('fileInput').files||[]);if(!files.length)return;
 for(const file of files){const url=URL.createObjectURL(file);const probe=document.createElement('video');probe.preload='metadata';probe.src=url;
  try{const duration=await new Promise((resolve,reject)=>{probe.onloadedmetadata=()=>resolve(probe.duration);probe.onerror=()=>reject(Error('파일을 읽을 수 없습니다: '+file.name));});clips.push({id:++clipSeq,file,url,duration,start:0,end:duration});}
  catch(e){URL.revokeObjectURL(url);alert(e.message);}
 }
 $('fileInput').value='';if(!selectedClipId&&clips.length)await selectClip(clips[0].id);else renderClips();
};
video.ontimeupdate=updateTime;
$('playBtn').onclick=async()=>{const c=selectedClip();if(!c)return;if(video.paused){if(video.currentTime<c.start||video.currentTime>=c.end)video.currentTime=c.start;try{await video.play();}catch(e){alert('재생을 시작할 수 없습니다: '+e.message);}}else video.pause();};
$('applyTrim').onclick=()=>{const c=selectedClip();if(!c)return;const a=Math.max(0,Number($('trimStart').value)||0),b=Math.min(c.duration,Number($('trimEnd').value)||c.duration);if(a>=b){alert('종료 시간은 시작 시간보다 커야 해요.');return;}c.start=a;c.end=b;renderClips();video.currentTime=a;};
video.addEventListener('timeupdate',()=>{const c=selectedClip();if(c&&!video.paused&&video.currentTime>=c.end)video.pause();});
$('captionText').oninput=updateCaption;$('captionColor').oninput=updateCaption;$('captionSize').oninput=updateCaption;$('clearCaption').onclick=()=>{$('captionText').value='';updateCaption();};
$('musicInput').onchange=()=>{const f=$('musicInput').files[0];if(!f)return;if(musicUrl)URL.revokeObjectURL(musicUrl);musicFile=f;musicUrl=URL.createObjectURL(f);if(musicEl){musicEl.pause();musicEl.remove();}musicEl=new Audio(musicUrl);musicEl.loop=true;musicEl.preload='auto';setMusicVolume();if(audioContext){try{musicAudioNode=audioContext.createMediaElementSource(musicEl);musicAudioNode.connect(audioContext.destination);musicAudioNode.connect(mixDestination);}catch(e){console.warn(e);}}$('musicStatus').textContent='선택됨: '+f.name;};
$('musicVolume').oninput=setMusicVolume;
$('removeMusic').onclick=()=>{if(musicEl){musicEl.pause();musicEl.remove();musicEl=null;}if(musicUrl)URL.revokeObjectURL(musicUrl);musicUrl=null;musicFile=null;musicAudioNode=null;$('musicInput').value='';$('musicStatus').textContent='배경 음악이 없습니다.';};
$('projectSaveBtn').onclick=()=>{
 const project={format:'NeoCutProject',version:2,clips:clips.map(c=>({name:c.file.name,start:c.start,end:c.end,duration:c.duration})),musicName:musicFile?.name||null,captionText:$('captionText').value,captionColor:$('captionColor').value,captionSize:Number($('captionSize').value),musicVolume:Number($('musicVolume').value)};
 const blob=new Blob([JSON.stringify(project,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='neocut-project.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
};
$('projectLoadBtn').onclick=()=>$('projectInput').click();
$('projectInput').onchange=async()=>{
 const f=$('projectInput').files[0];if(!f)return;
 try{const p=JSON.parse(await f.text());if(p.format!=='NeoCutProject'||![1,2].includes(p.version))throw Error('지원하지 않는 프로젝트 파일입니다.');
  $('captionText').value=String(p.captionText||'');$('captionColor').value=/^#[0-9a-f]{6}$/i.test(p.captionColor)?p.captionColor:'#ffffff';$('captionSize').value=Math.min(54,Math.max(18,Number(p.captionSize)||30));$('musicVolume').value=Math.min(1,Math.max(0,Number(p.musicVolume)||0));setMusicVolume();updateCaption();
  if(p.version===2&&Array.isArray(p.clips)){const names=p.clips.map(c=>c.name).filter(Boolean);alert('편집 설정을 불러왔어요. 저장된 클립 순서: '+(names.join(', ')||'없음')+'。 영상 파일 자체는 저장되지 않으므로 파일을 다시 불러와야 하며, 현재 버전에서는 자동 연결되지 않습니다.');}
  else alert('편집 설정을 불러왔어요. 영상과 음악 파일은 별도로 다시 선택해야 합니다.');
 }catch(e){alert('프로젝트 열기 실패: '+e.message);}finally{$('projectInput').value='';}
};
$('exportBtn').onclick=async()=>{
 if(!clips.length)return;const btn=$('exportBtn');btn.disabled=true;btn.textContent='여러 클립 내보내는 중…';let recorder=null,raf=0,stream=null;
 try{
  if(!window.MediaRecorder||!HTMLCanvasElement.prototype.captureStream)throw Error('이 브라우저는 WebM 녹화를 지원하지 않습니다.');
  initAudio();await audioContext.resume();
  const canvas=document.createElement('canvas');canvas.width=1280;canvas.height=720;const ctx=canvas.getContext('2d');stream=canvas.captureStream(30);mixDestination.stream.getAudioTracks().forEach(t=>stream.addTrack(t));
  const mime=['video/webm;codecs=vp9,opus','video/webm;codecs=vp8,opus','video/webm'].find(t=>MediaRecorder.isTypeSupported(t));if(!mime)throw Error('지원되는 WebM 녹화 형식이 없습니다.');
  recorder=new MediaRecorder(stream,{mimeType:mime});const chunks=[];recorder.ondataavailable=e=>{if(e.data.size)chunks.push(e.data);};
  const finished=new Promise((resolve,reject)=>{recorder.onstop=resolve;recorder.onerror=()=>reject(Error('녹화에 실패했어요.'));});
  const draw=()=>{ctx.fillStyle='#000';ctx.fillRect(0,0,canvas.width,canvas.height);if(video.readyState>=2){const scale=Math.min(canvas.width/video.videoWidth,canvas.height/video.videoHeight),w=video.videoWidth*scale,h=video.videoHeight*scale;ctx.drawImage(video,(canvas.width-w)/2,(canvas.height-h)/2,w,h);}const txt=$('captionText').value;if(txt){const size=Number($('captionSize').value);ctx.font='800 '+size+'px sans-serif';ctx.textAlign='center';ctx.textBaseline='bottom';ctx.lineWidth=Math.max(3,size/8);ctx.strokeStyle='#000';ctx.fillStyle=$('captionColor').value;ctx.strokeText(txt,canvas.width/2,canvas.height*.9,canvas.width*.9);ctx.fillText(txt,canvas.width/2,canvas.height*.9,canvas.width*.9);}if(recorder&&recorder.state==='recording')raf=requestAnimationFrame(draw);};
  video.pause();if(musicEl)musicEl.pause();recorder.start(250);draw();if(musicEl){musicEl.currentTime=0;musicEl.play().catch(()=>{});}
  for(let i=0;i<clips.length;i++){
   const c=clips[i];$('clipName').textContent='내보내기 '+(i+1)+' / '+clips.length+': '+c.file.name;
   if(video.src!==c.url){video.src=c.url;video.load();await waitMetadata();}
   video.currentTime=Math.min(c.start,Math.max(0,c.duration-.05));await new Promise((resolve,reject)=>{const done=()=>{video.removeEventListener('seeked',done);resolve();};video.addEventListener('seeked',done,{once:true});setTimeout(done,1200);});
   await video.play();
   await new Promise((resolve,reject)=>{
    let settled=false;const finish=()=>{if(settled)return;settled=true;video.removeEventListener('timeupdate',check);video.removeEventListener('ended',finish);video.removeEventListener('error',fail);video.pause();resolve();};
    const check=()=>{if(video.currentTime>=c.end)finish();};
    const fail=()=>{if(settled)return;settled=true;reject(Error('클립 재생 실패: '+c.file.name));};
    video.addEventListener('timeupdate',check);video.addEventListener('ended',finish,{once:true});video.addEventListener('error',fail,{once:true});check();
   });
  }
  await new Promise(resolve=>setTimeout(resolve,300));if(recorder.state==='recording')recorder.stop();await finished;cancelAnimationFrame(raf);
  const blob=new Blob(chunks,{type:mime});if(!blob.size)throw Error('내보낸 파일이 비어 있습니다.');const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download='neocut-edited.webm';link.click();setTimeout(()=>URL.revokeObjectURL(url),30000);
  if(musicEl)musicEl.pause();
 }catch(e){if(recorder&&recorder.state==='recording')recorder.stop();alert('내보내기 오류: '+e.message+'\n다른 최신 브라우저에서 다시 시도해 주세요.');}
 finally{cancelAnimationFrame(raf);if(stream)stream.getTracks().forEach(t=>t.stop());video.ontimeupdate=updateTime;btn.disabled=!clips.length;btn.textContent='내보내기 (WebM)';renderClips();updateTime();}
};
updateCaption();renderClips();
