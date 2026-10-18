let deferredInstallPrompt=null;
const installButton=document.getElementById('installBtn');
window.addEventListener('beforeinstallprompt',event=>{
  event.preventDefault();
  deferredInstallPrompt=event;
  if(installButton) installButton.hidden=false;
});
if(installButton){
  installButton.addEventListener('click',async()=>{
    if(!deferredInstallPrompt){
      alert('설치 메뉴가 표시되지 않으면 브라우저 메뉴에서 “앱 설치” 또는 “홈 화면에 추가”를 찾아보세요.');
      return;
    }
    deferredInstallPrompt.prompt();
    await deferredInstallPrompt.userChoice;
    deferredInstallPrompt=null;
    installButton.hidden=true;
  });
}
window.addEventListener('appinstalled',()=>{
  if(installButton) installButton.hidden=true;
});
if('serviceWorker' in navigator && (location.protocol==='https:' || location.hostname==='localhost')){
  window.addEventListener('load',()=>{
    navigator.serviceWorker.register('./sw.js').catch(err=>console.warn('NeoCut offline cache unavailable:',err));
  });
}
