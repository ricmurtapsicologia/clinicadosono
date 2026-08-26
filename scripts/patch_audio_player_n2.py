from pathlib import Path

p=Path('index.html')
s=p.read_text(encoding='utf-8')
start=s.find('function buildAudioScript(d)')
end=s.find('function renderHome()',start)
if start<0 or end<0:
    if 'new Audio(chapterAudioUrl(d))' in s and 'speechSynthesis' not in s:
        print('Player N2 já aplicado.')
        raise SystemExit(0)
    raise SystemExit('Bloco legado de áudio não localizado')

replacement="""const AUDIO_N2_VERSION='n2-20260825';
let chapterAudio=null;
function chapterAudioUrl(d){return `./audio/n2/chapter-${String(d.num).padStart(2,'0')}.mp3?v=${AUDIO_N2_VERSION}`}
function updateAudioUI(message){const play=$('#audioPlay'),status=$('#audioStatus');if(play){if(audioState.playing&&audioState.paused)play.textContent='▶ Continuar';else if(audioState.playing)play.textContent='⏸ Pausar';else play.textContent='▶ Ouvir áudio'}if(status&&message)status.textContent=message}
function persistAudio(){if(!chapterAudio||!audioState.chapter||!Number.isFinite(chapterAudio.currentTime))return;try{const m=JSON.parse(localStorage.getItem('tcci.audio.n2')||'{}');m[audioState.chapter]=Math.floor(chapterAudio.currentTime);localStorage.setItem('tcci.audio.n2',JSON.stringify(m))}catch(e){}}
function stopAudio(message='Pronto para ouvir.'){audioToken++;if(chapterAudio){persistAudio();chapterAudio.pause();chapterAudio.removeAttribute('src');try{chapterAudio.load()}catch(e){}}chapterAudio=null;audioState={chapter:'',chunks:[],index:0,playing:false,paused:false};updateAudioUI(message)}
function toggleAudio(d){
  if(audioState.playing&&audioState.chapter===d.id&&chapterAudio){
    if(audioState.paused){chapterAudio.play().then(()=>{audioState.paused=false;updateAudioUI('Reproduzindo resumo do capítulo…')}).catch(()=>updateAudioUI('Áudio temporariamente indisponível.'))}
    else{chapterAudio.pause();audioState.paused=true;persistAudio();updateAudioUI('Áudio pausado.')}
    return
  }
  stopAudio();audioState={chapter:d.id,chunks:[],index:0,playing:true,paused:false};
  chapterAudio=new Audio(chapterAudioUrl(d));chapterAudio.preload='metadata';
  chapterAudio.addEventListener('loadedmetadata',()=>{try{const m=JSON.parse(localStorage.getItem('tcci.audio.n2')||'{}');const t=Number(m[d.id]||0);if(t>0&&t<chapterAudio.duration-2)chapterAudio.currentTime=t}catch(e){}},{once:true});
  chapterAudio.addEventListener('timeupdate',()=>{if(Math.floor(chapterAudio.currentTime)%5===0)persistAudio()});
  chapterAudio.addEventListener('ended',()=>{try{const m=JSON.parse(localStorage.getItem('tcci.audio.n2')||'{}');delete m[d.id];localStorage.setItem('tcci.audio.n2',JSON.stringify(m))}catch(e){}audioState.playing=false;audioState.paused=false;chapterAudio=null;updateAudioUI('Áudio concluído.')});
  chapterAudio.addEventListener('error',()=>{audioState.playing=false;audioState.paused=false;updateAudioUI('Áudio temporariamente indisponível.')});
  updateAudioUI('Reproduzindo resumo do capítulo…');chapterAudio.play().catch(()=>{audioState.playing=false;updateAudioUI('Áudio temporariamente indisponível.')})
}
"""
s=s[:start]+replacement+s[end:]
if 'speechSynthesis' in s or 'SpeechSynthesisUtterance' in s:
    raise SystemExit('Ainda existe SpeechSynthesis em index.html')
p.write_text(s,encoding='utf-8')
print('Player MP3 N2 aplicado aos 28 capítulos.')
