from __future__ import annotations

import asyncio, base64, gzip, hashlib, json, re, shutil
from pathlib import Path

import edge_tts
from bs4 import BeautifulSoup
from pydub import AudioSegment, effects

ROOT=Path(__file__).resolve().parents[1]
PAYLOADS=['payload4/c1a.txt','payload4/c1b.txt','payload4/c1c.txt','payload4/c1d.txt','payload4/c2a.txt','payload4/c2b.txt','payload4/c2c.txt','payload4/c2d.txt','payload3/c3a.txt','payload3/c3b.txt','payload4/c3c.txt','payload4/c3d.txt','payload4/c4a.txt','payload4/c4b.txt','payload4/c4c.txt','payload4/c4d.txt']
OUT=ROOT/'audio/n3';ROTEIROS=ROOT/'roteiros/audio-n3';TMP=ROOT/'.tmp_chapter_audio_n3'
VOICE='pt-BR-AntonioNeural';VERSION='n3-20260831';MAX_WORDS=430;TARGET_DBFS=-18.0
SOFT={'mas','porém','porem','contudo','entretanto','porque','quando','enquanto','então','entao','assim','agora','portanto','se','como','além','alem','ainda','depois','antes','embora'}
INSTRUCTIONS=('observe','imagine','pense','perceba','note','considere','guarde','repare')
CONCLUSION=('em resumo','para concluir','por fim','em síntese','em sintese','o ponto principal')


def norm(t):return re.sub(r'\s+',' ',t or '').strip()
def tokens(t):return re.findall(r'[\wÀ-ÿ]+',t.lower(),flags=re.UNICODE)
def stable(text,lo,hi,salt):
    h=hashlib.sha256((salt+'|'+norm(text)).encode()).digest();u=int.from_bytes(h[:4],'big')/0xffffffff
    return lo+int(round(u*(hi-lo)))
def classify(text):
    t=norm(text);low=t.lower()
    if t.endswith('?'):return 'question'
    if low.startswith(INSTRUCTIONS):return 'instruction'
    if low.startswith(CONCLUSION):return 'conclusion'
    if t.endswith('!'):return 'emphasis'
    return 'explain'
def breath_units(text):
    text=norm(text);out=[]
    for sentence in [s.strip() for s in re.split(r'(?<=[.!?…])\s+',text) if s.strip()]:
        words=sentence.split()
        if len(words)<=20:out.append(sentence);continue
        start=0
        while len(words)-start>20:
            lo=start+9;hi=min(start+20,len(words));target=min(start+14,hi);cand=[]
            for i in range(lo,hi):
                w=re.sub(r'^[^\wÀ-ÿ]+|[^\wÀ-ÿ]+$','',words[i].lower())
                if w in SOFT:cand.append(i)
            cut=min(cand,key=lambda i:abs(i-target)) if cand else target
            unit=' '.join(words[start:cut]).strip()
            if unit and not unit.endswith((',', ';', ':', '.', '?', '!', '…')):unit+=','
            out.append(unit);start=cut
        if start<len(words):out.append(' '.join(words[start:]).strip())
    if tokens(' '.join(out))!=tokens(text):raise RuntimeError('Gate lexical N3 falhou')
    return out

def prosody(text):
    i=classify(text);rate=-4+{'explain':0,'question':1,'instruction':-3,'conclusion':-2,'emphasis':1}[i];pitch=-1+{'explain':0,'question':2,'instruction':-1,'conclusion':-1,'emphasis':1}[i]
    rate+=stable(text,-1,1,'rate');pitch+=stable(text,-1,1,'pitch')
    ranges={'explain':(390,650),'question':(480,760),'instruction':(760,1250),'conclusion':(650,1050),'emphasis':(390,650)}
    lo,hi=ranges[i];return i,f'{max(-12,min(4,rate)):+d}%',f'{max(-5,min(5,pitch)):+d}Hz',stable(text,lo,hi,'pause')


def load_docs():
    missing=[p for p in PAYLOADS if not (ROOT/p).exists()]
    if missing:raise RuntimeError(f'Payloads ausentes: {missing}')
    b64=''.join(re.sub(r'\s+','',(ROOT/p).read_text(encoding='utf-8')) for p in PAYLOADS)
    docs=json.loads(gzip.decompress(base64.b64decode(b64)).decode('utf-8'))
    chapters=[d for d in docs if 1<=int(d.get('num') or 0)<=28];chapters.sort(key=lambda d:int(d['num']))
    if len(chapters)!=28:raise RuntimeError(f'Esperados 28 capítulos; encontrados {len(chapters)}')
    return chapters

def build_audio_script(d):
    soup=BeautifulSoup(d.get('html') or '','html.parser');paras=[norm(p.get_text(' ',strip=True)) for p in soup.find_all('p')];paras=[p for p in paras if len(p)>45];heads=soup.find_all(['h2','h3']);used=set()
    parts=[f"Neste áudio explicativo, vamos revisar os principais pontos do capítulo {d['num']}, {norm(d.get('title'))}. O objetivo é organizar os conceitos centrais e destacar como eles se conectam ao raciocínio clínico em TCC-I."]
    for p in paras[:2]:parts.append(p);used.add(p)
    for h in heads[:8]:
        ht=norm(h.get_text(' ',strip=True));n=h.find_next_sibling();p=''
        while n is not None:
            if getattr(n,'name',None)=='p':p=norm(n.get_text(' ',strip=True));break
            if getattr(n,'name',None) in ('h2','h3'):break
            n=n.find_next_sibling()
        if ht and p and len(p)>45:parts.append(f'Um ponto importante é {ht}. {p}');used.add(p)
    text=norm(' '.join(parts));count=len(text.split())
    for p in paras:
        if count>=MAX_WORDS:break
        if p in used:continue
        text=norm(text+' '+p);count=len(text.split())
    words=text.split()[:MAX_WORDS]
    return ' '.join(words)+('…' if count>MAX_WORDS else '')

async def synth(text,rate,pitch,path,sem):
    async with sem:
        for attempt in range(1,4):
            try:
                c=edge_tts.Communicate(text=text,voice=VOICE,rate=rate,pitch=pitch,volume='+0%');await asyncio.wait_for(c.save(str(path)),timeout=55);return
            except Exception:
                if attempt==3:raise
                await asyncio.sleep(.9*attempt)
async def render(d,sem):
    num=int(d['num']);key=f'chapter-{num:02d}';script=build_audio_script(d);ROTEIROS.mkdir(parents=True,exist_ok=True);(ROTEIROS/f'{key}.txt').write_text(script+'\n',encoding='utf-8')
    turns=breath_units(script);work=TMP/key;work.mkdir(parents=True,exist_ok=True);tasks=[];seq=[];intents=[]
    for i,turn in enumerate(turns):
        intent,rate,pitch,pause=prosody(turn);part=work/f'{i:03d}.mp3';seq.append((part,0 if i==len(turns)-1 else pause));tasks.append(synth(turn,rate,pitch,part,sem));intents.append(intent)
    await asyncio.gather(*tasks);audio=AudioSegment.silent(duration=150)
    for part,pause in seq:
        audio+=AudioSegment.from_file(part,format='mp3')
        if pause:audio+=AudioSegment.silent(duration=pause)
    audio+=AudioSegment.silent(duration=280);audio=effects.compress_dynamic_range(audio,threshold=-20.0,ratio=2.0,attack=8.0,release=70.0)
    if audio.dBFS!=float('-inf'):audio=audio.apply_gain(TARGET_DBFS-audio.dBFS)
    if audio.max_dBFS>-1.2:audio=audio.apply_gain(-1.2-audio.max_dBFS)
    OUT.mkdir(parents=True,exist_ok=True);target=OUT/f'{key}.mp3';audio.export(target,format='mp3',bitrate='128k',parameters=['-ac','1','-ar','44100'])
    return {'id':key,'chapter':num,'title':norm(d.get('title')),'url':f'./audio/n3/{key}.mp3?v={VERSION}','duration_seconds':round(len(audio)/1000,1),'turns':len(turns),'intents':sorted(set(intents))}

async def main():
    docs=load_docs();OUT.mkdir(parents=True,exist_ok=True);TMP.mkdir(parents=True,exist_ok=True);sem=asyncio.Semaphore(4);rows=[]
    for d in docs:rows.append(await render(d,sem))
    manifest={'version':VERSION,'voice':VOICE,'profile':'N3-C Natural — Clínica do Sono','format':'MP3 128 kbps, mono, 44.1 kHz','tracks':rows}
    (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (OUT/'audio-spec.json').write_text(json.dumps({'version':VERSION,'voice':VOICE,'profile':'N3-C Natural — explain','prosody':'semantic-intent + respiratory-units + deterministic-content-jitter','ambient_audio':False,'target_dbfs':TARGET_DBFS,'peak_ceiling_dbfs':-1.2,'format':'MP3 128 kbps, mono, 44.1 kHz','track_count':28},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    shutil.rmtree(TMP,ignore_errors=True);print('Concluído: 28 capítulos N3-C.')

if __name__=='__main__':asyncio.run(main())
