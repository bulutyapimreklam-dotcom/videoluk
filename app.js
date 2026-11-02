const $=(s,r=document)=>r.querySelector(s), $$=(s,r=document)=>[...r.querySelectorAll(s)];
const state={type:'Sosyal Medya',duration:30,orientation:'vertical',source:'Yapay zekâ',selected:0,playing:false,zoom:100,scenes:[
 {title:'Şehir seninle yeniden ritim bulur.',sub:'Her adım, daha canlı bir geleceğe.',time:'0–7 sn'},
 {title:'Yeni fikirler aynı sokakta buluşur.',sub:'İlham her köşede.',time:'7–18 sn'},
 {title:'Geleceğin ritmini sen belirle.',sub:'Şimdi harekete geç.',time:'18–30 sn'}]};
function go(n){$$('.panel').forEach(p=>p.classList.remove('active'));$('#step-'+n).classList.add('active');$$('.step').forEach((s,i)=>s.classList.toggle('active',i<n));scrollTo(0,0)}
$$('[data-next]').forEach(b=>b.onclick=()=>go(b.dataset.next));
$$('.type-card').forEach(b=>b.onclick=()=>{$$('.type-card').forEach(x=>x.classList.remove('selected'));b.classList.add('selected');state.type=b.dataset.type;$('#projectType').textContent=state.type});
$('#duration').oninput=e=>{state.duration=+e.target.value;$('#durationOut').textContent=state.duration+' saniye';$('#projectDuration').textContent=state.duration+' sn'};
$$('.source-toggle button').forEach(b=>b.onclick=()=>{$$('.source-toggle button').forEach(x=>x.classList.remove('selected'));b.classList.add('selected');state.source=b.dataset.source});
$$('.orientation-toggle button').forEach(b=>b.onclick=()=>{$$('.orientation-toggle button').forEach(x=>x.classList.remove('selected'));b.classList.add('selected');state.orientation=b.dataset.orientation});
$('#script').oninput=e=>$('#charCount').textContent=e.target.value.length+' / 800';
$$('.example-prompts button').forEach(b=>b.onclick=()=>{$('#script').value=b.textContent.replaceAll('“','').replaceAll('”','');$('#script').dispatchEvent(new Event('input'))});
$('.chip').onclick=()=>{$('#script').value='Şehrin yoğun temposunda küçük seçimlerin nasıl büyük ve pozitif bir değişim yaratabileceğini; enerjik, umut veren ve modern bir anlatımla göster.';$('#script').dispatchEvent(new Event('input'))};
$('#voicePlay').onclick=e=>{e.currentTarget.textContent='◼ Oynatılıyor';setTimeout(()=>e.currentTarget.textContent='▶ Dinle',1600)};
$('#generateBtn').onclick=()=>{const b=$('#generateBtn');b.innerHTML='Sahneler hazırlanıyor <span>···</span>';setTimeout(()=>{prepareStudio();renderScenes();go(3);b.innerHTML='Sahneleri oluştur <span>✦</span>'},900)};
function prepareStudio(){const fmt=s=>`00:${String(s).padStart(2,'0')}`;const formats={vertical:{res:'1080 × 1920',ratio:'9 / 16'},horizontal:{res:'1920 × 1080',ratio:'16 / 9'},square:{res:'1080 × 1080',ratio:'1 / 1'}};const f=formats[state.orientation];$('#canvasResolution').textContent=f.res;$('#renderResolution').textContent=f.res;$('#canvasDuration').textContent=fmt(state.duration);$('#timelineDuration').textContent=fmt(state.duration);$('#rulerEnd').textContent=fmt(state.duration);$('#renderDuration').textContent=state.duration;$('#videoCanvas').style.aspectRatio=f.ratio;}
function renderScenes(){
 $('#sceneCards').innerHTML=state.scenes.map((s,i)=>`<div class="scene-card ${i===state.selected?'selected':''}" data-i="${i}"><div class="thumb">${s.title}</div><div class="scene-meta"><b>Sahne ${String(i+1).padStart(2,'0')}</b><span>${s.time}</span></div></div>`).join('');
 $('#videoClips').innerHTML=state.scenes.map((s,i)=>`<div class="clip ${i===state.selected?'selected':''}" data-i="${i}">Sahne ${i+1}<br>${s.time}</div>`).join('');
 $$('[data-i]').forEach(x=>x.onclick=()=>selectScene(+x.dataset.i));
 const s=state.scenes[state.selected]; if(s){$('#canvasTitle').innerHTML=s.title.replace(' yeniden','<br>yeniden');$('#canvasSubtitle').textContent=s.sub}
}
function selectScene(i){state.selected=i;renderScenes()}
$('#addScene').onclick=()=>{state.scenes.push({title:'Yeni sahne',sub:'Mesajını buraya ekle.',time:'30–35 sn'});state.selected=state.scenes.length-1;renderScenes();toast('Yeni sahne eklendi')};
$('#deleteScene').onclick=()=>{if(state.scenes.length===1)return toast('En az bir sahne kalmalı');state.scenes.splice(state.selected,1);state.selected=Math.max(0,state.selected-1);renderScenes();toast('Sahne silindi')};
$('#splitScene').onclick=()=>{const s=state.scenes[state.selected];state.scenes.splice(state.selected+1,0,{...s,title:s.title+' · devam'});renderScenes();toast('Sahne ikiye bölündü')};
function togglePlay(){state.playing=!state.playing;$('#canvasPlay').textContent=state.playing?'Ⅱ':'▶';$('#playOverlay').textContent=state.playing?'Ⅱ':'▶';if(state.playing){let t=0;const int=setInterval(()=>{if(!state.playing||t>=state.duration){clearInterval(int);state.playing=false;$('#canvasPlay').textContent='▶';return}t++;$('#currentTime').textContent='00:'+String(t).padStart(2,'0')},1000)}}
$('#canvasPlay').onclick=togglePlay;$('#playOverlay').onclick=togglePlay;$('#previewBtn').onclick=togglePlay;
$('#zoomIn').onclick=()=>{$('#zoomValue').textContent=(state.zoom=Math.min(150,state.zoom+10))+'%'};$('#zoomOut').onclick=()=>{$('#zoomValue').textContent=(state.zoom=Math.max(50,state.zoom-10))+'%'};
$('#renderBtn').onclick=()=>{$('#renderModal').classList.add('open');$('#renderModal').setAttribute('aria-hidden','false')};$('#closeModal').onclick=()=>$('#renderModal').classList.remove('open');$('#downloadBtn').onclick=()=>toast('Demo video indirmeye hazırlandı');
$('#downloadTopBtn').onclick=()=>{$('#renderModal').classList.add('open');toast('İndirme seçenekleri hazır')};
$('#captionEnabled').onchange=e=>$('#captionPreview').style.display=e.target.checked?'block':'none';
$('#captionPosition').onchange=e=>{$('#captionPreview').classList.remove('top','middle');if(e.target.value!=='bottom')$('#captionPreview').classList.add(e.target.value)};
$$('.caption-styles button').forEach(b=>b.onclick=()=>{$$('.caption-styles button').forEach(x=>x.classList.remove('selected'));b.classList.add('selected');$('#captionPreview').classList.remove('bold','minimal');if(b.dataset.captionStyle!=='classic')$('#captionPreview').classList.add(b.dataset.captionStyle)});
function toast(msg){const t=$('#toast');t.textContent=msg;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),1800)}
renderScenes();
