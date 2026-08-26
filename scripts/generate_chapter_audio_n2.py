from __future__ import annotations

import asyncio
import base64
import gzip
import json
import re
import shutil
from pathlib import Path

import edge_tts
from bs4 import BeautifulSoup
from pydub import AudioSegment, effects

ROOT = Path(__file__).resolve().parents[1]
PAYLOADS = [
    'payload4/c1a.txt','payload4/c1b.txt','payload4/c1c.txt','payload4/c1d.txt',
    'payload4/c2a.txt','payload4/c2b.txt','payload4/c2c.txt','payload4/c2d.txt',
    'payload3/c3a.txt','payload3/c3b.txt','payload4/c3c.txt','payload4/c3d.txt',
    'payload4/c4a.txt','payload4/c4b.txt','payload4/c4c.txt','payload4/c4d.txt',
]
OUT = ROOT / 'audio/n2'
ROTEIROS = ROOT / 'roteiros/audio-n2'
TMP = ROOT / '.tmp_chapter_audio_n2'
VOICE = 'pt-BR-AntonioNeural'
VERSION = 'n2-20260825'
OPENING_SILENCE_MS = 130
ENDING_SILENCE_MS = 240
TARGET_DBFS = -18.0
MAX_TURN_CHARS = 560
MAX_WORDS = 430


def normalize(text: str) -> str:
    return re.sub(r'\s+', ' ', text or '').strip()


def load_docs() -> list[dict]:
    missing = [p for p in PAYLOADS if not (ROOT / p).exists()]
    if missing:
        raise RuntimeError(f'Payloads ausentes: {missing}')
    b64 = ''.join(re.sub(r'\s+', '', (ROOT / p).read_text(encoding='utf-8')) for p in PAYLOADS)
    raw = gzip.decompress(base64.b64decode(b64))
    docs = json.loads(raw.decode('utf-8'))
    chapters = [d for d in docs if 1 <= int(d.get('num') or 0) <= 28]
    if len(chapters) != 28:
        raise RuntimeError(f'Esperados 28 capítulos; encontrados {len(chapters)}')
    chapters.sort(key=lambda d: int(d['num']))
    return chapters


def build_audio_script(d: dict) -> str:
    soup = BeautifulSoup(d.get('html') or '', 'html.parser')
    paras = [normalize(p.get_text(' ', strip=True)) for p in soup.find_all('p')]
    paras = [p for p in paras if len(p) > 45]
    heads = soup.find_all(['h2', 'h3'])
    used: set[str] = set()
    parts = [
        f"Neste áudio explicativo, vamos revisar os principais pontos do capítulo {d['num']}, {normalize(d.get('title'))}. "
        "O objetivo é organizar os conceitos centrais e destacar como eles se conectam ao raciocínio clínico em TCC-I."
    ]
    for p in paras[:2]:
        parts.append(p); used.add(p)
    for h in heads[:8]:
        ht = normalize(h.get_text(' ', strip=True))
        n = h.find_next_sibling()
        p = ''
        while n is not None:
            if getattr(n, 'name', None) == 'p':
                p = normalize(n.get_text(' ', strip=True)); break
            if getattr(n, 'name', None) in ('h2', 'h3'):
                break
            n = n.find_next_sibling()
        if ht and p and len(p) > 45:
            parts.append(f'Um ponto importante é {ht}. {p}')
            used.add(p)
    text = normalize(' '.join(parts))
    count = len(text.split())
    for p in paras:
        if count >= MAX_WORDS: break
        if p in used: continue
        text = normalize(text + ' ' + p)
        count = len(text.split())
    words = text.split()[:MAX_WORDS]
    return ' '.join(words) + ('…' if count > MAX_WORDS else '')


def split_turns(text: str) -> list[str]:
    sentences = re.findall(r'[^.!?…]+[.!?…]+|[^.!?…]+$', normalize(text))
    turns=[]; current=''
    for sentence in map(normalize, sentences):
        if not sentence: continue
        candidate = normalize(current + ' ' + sentence)
        if current and len(candidate) > MAX_TURN_CHARS:
            turns.append(current); current = sentence
        else:
            current = candidate
    if current: turns.append(current)
    return turns


def prosody(text: str, i: int):
    rate=-4; pitch=-1
    low=text.lower().strip()
    if text.rstrip().endswith('?'):
        rate += 2; pitch += 2; pause=560
    elif text.rstrip().endswith('!'):
        pause=500
    else:
        pause=520
    if low.startswith(('guarde','em resumo','pense','imagine','observe','agora','por enquanto','o ponto')):
        rate -= 2
    rate += (-1,0,1,0)[i%4]
    return f'{max(-10,min(4,rate)):+d}%', f'{max(-4,min(4,pitch)):+d}Hz', pause


async def synth(text: str, rate: str, pitch: str, path: Path, sem: asyncio.Semaphore):
    async with sem:
        for attempt in range(1,4):
            try:
                c=edge_tts.Communicate(text=text,voice=VOICE,rate=rate,pitch=pitch,volume='+0%')
                await asyncio.wait_for(c.save(str(path)), timeout=55)
                return
            except Exception:
                if attempt == 3: raise
                await asyncio.sleep(.9*attempt)


async def render(d: dict, sem: asyncio.Semaphore) -> dict:
    num=int(d['num']); key=f'chapter-{num:02d}'
    script=build_audio_script(d)
    ROTEIROS.mkdir(parents=True, exist_ok=True)
    (ROTEIROS/f'{key}.txt').write_text(script+'\n',encoding='utf-8')
    turns=split_turns(script)
    work=TMP/key; work.mkdir(parents=True, exist_ok=True)
    tasks=[]; seq=[]
    for i,turn in enumerate(turns):
        rate,pitch,pause=prosody(turn,i)
        part=work/f'{i:03d}.mp3'; seq.append((part,0 if i==len(turns)-1 else pause))
        tasks.append(synth(turn,rate,pitch,part,sem))
    await asyncio.gather(*tasks)
    audio=AudioSegment.silent(duration=OPENING_SILENCE_MS)
    for part,pause in seq:
        audio += AudioSegment.from_file(part,format='mp3')
        if pause: audio += AudioSegment.silent(duration=pause)
    audio += AudioSegment.silent(duration=ENDING_SILENCE_MS)
    audio=effects.compress_dynamic_range(audio,threshold=-20.0,ratio=2.0,attack=8.0,release=70.0)
    if audio.dBFS != float('-inf'): audio=audio.apply_gain(TARGET_DBFS-audio.dBFS)
    if audio.max_dBFS > -1.2: audio=audio.apply_gain(-1.2-audio.max_dBFS)
    target=OUT/f'{key}.mp3'
    audio.export(target,format='mp3',bitrate='128k',parameters=['-ac','1','-ar','44100'])
    seconds=round(len(audio)/1000,1)
    print(f'{key}: {seconds}s')
    return {'id':key,'chapter':num,'title':normalize(d.get('title')),'url':f'./audio/n2/{key}.mp3?v={VERSION}','duration_seconds':seconds}


async def main():
    docs=load_docs(); OUT.mkdir(parents=True,exist_ok=True); TMP.mkdir(exist_ok=True)
    sem=asyncio.Semaphore(4); rows=[]
    for d in docs: rows.append(await render(d,sem))
    if len(rows)!=28: raise RuntimeError('Falha na geração dos 28 capítulos')
    manifest={
        'version':VERSION,'voice':VOICE,
        'profile':'Padrão Sonoro Clínico Richelmy Murta — Sono em Dia / Ampulheta N2',
        'format':'MP3 128 kbps, mono, 44.1 kHz','tracks':rows,
    }
    (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (OUT/'audio-spec.json').write_text(json.dumps({
        'voice':VOICE,'profile':'Sono em Dia / Ampulheta N2 — explain','opening_silence_ms':OPENING_SILENCE_MS,
        'ending_silence_ms':ENDING_SILENCE_MS,'target_dbfs':TARGET_DBFS,'peak_ceiling_dbfs':-1.2,
        'compression':{'threshold_db':-20.0,'ratio':2.0,'attack_ms':8.0,'release_ms':70.0},
        'format':'MP3 128 kbps, mono, 44.1 kHz','track_count':28
    },ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    shutil.rmtree(TMP,ignore_errors=True)

if __name__=='__main__': asyncio.run(main())
