from pathlib import Path
import re

p=Path('index.html');s=p.read_text(encoding='utf-8')
# Migração idempotente do player MP3 já existente.
s=s.replace("const AUDIO_N2_VERSION='n2-20260825';","const AUDIO_N3_VERSION='n3-20260831';")
s=s.replace('AUDIO_N2_VERSION','AUDIO_N3_VERSION')
s=s.replace('./audio/n2/chapter-','./audio/n3/chapter-')
s=s.replace("'tcci.audio.n2'","'tcci.audio.n3'")
s=s.replace('Player N2','Player N3')
if 'speechSynthesis' in s or 'SpeechSynthesisUtterance' in s:
    raise SystemExit('Ainda existe SpeechSynthesis em index.html')
if './audio/n3/chapter-' not in s or 'AUDIO_N3_VERSION' not in s:
    raise SystemExit('Player N3 não foi aplicado corretamente')
p.write_text(s,encoding='utf-8')
print('Player MP3 N3 aplicado aos 28 capítulos.')
