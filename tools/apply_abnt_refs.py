import base64, gzip, json, re, unicodedata, html, sys
from pathlib import Path
from bs4 import BeautifulSoup
from pybtex.database import parse_file
from pylatexenc.latex2text import LatexNodes2Text

ROOT=Path('.')
SRC=Path(sys.argv[1] if len(sys.argv)>1 else '/tmp/tcci-src')
ACCESS='25 ago. 2026'
latex=LatexNodes2Text()

payload_names=['payload4/c1a.txt','payload4/c1b.txt','payload4/c1c.txt','payload4/c1d.txt','payload4/c2a.txt','payload4/c2b.txt','payload4/c2c.txt','payload4/c2d.txt','payload3/c3a.txt','payload3/c3b.txt','payload4/c3c.txt','payload4/c3d.txt','payload4/c4a.txt','payload4/c4b.txt','payload4/c4c.txt','payload4/c4d.txt']
b64=''.join((ROOT/n).read_text(encoding='utf-8').replace('\n','').replace('\r','').replace(' ','') for n in payload_names)
docs=json.loads(gzip.decompress(base64.b64decode(b64)).decode('utf-8'))
chapters=[d for d in docs if isinstance(d.get('num'),int) and 1 <= d['num'] <= 28]

bib_candidates=list(SRC.rglob('references.bib')) or list(SRC.rglob('*.bib'))
if not bib_candidates:
    raise SystemExit('Nenhum arquivo BibTeX encontrado na fonte do projeto.')
bib_path=bib_candidates[0]
bib=parse_file(str(bib_path))

def txt(v):
    if not v: return ''
    try: v=latex.latex_to_text(str(v))
    except Exception: v=str(v)
    return re.sub(r'\s+',' ',v.replace('{','').replace('}','')).strip()

def norm(v):
    v=txt(v).lower()
    v=''.join(c for c in unicodedata.normalize('NFD',v) if unicodedata.category(c)!='Mn')
    v=v.replace('&',' e ')
    v=re.sub(r'[^a-z0-9]+',' ',v)
    return re.sub(r'\s+',' ',v).strip()

def js_ref_key(v):
    v=txt(v)
    v=''.join(c for c in unicodedata.normalize('NFD',v) if unicodedata.category(c)!='Mn').lower()
    v=re.sub(r'[().,;:]',' ',v)
    return re.sub(r'\s+',' ',v).strip()

def person_text(p):
    family=txt(' '.join(list(p.prelast_names)+list(p.last_names)+list(p.lineage_names))).strip()
    given=txt(' '.join(list(p.first_names)+list(p.middle_names))).strip()
    if not family: family,given=given,''
    return family.upper()+(', '+given if given else '')

def author_string(e,role='author'):
    people=e.persons.get(role,[])
    if not people: return ''
    vals=[person_text(p) for p in people]
    return vals[0]+' et al.' if len(vals)>=4 else '; '.join(vals)

def surnames(e):
    out=[]
    for p in e.persons.get('author',[]):
        fam=txt(' '.join(list(p.prelast_names)+list(p.last_names)+list(p.lineage_names))).strip()
        if fam: out.append(norm(fam))
    return out

def acronym(s):
    words=[w for w in re.findall(r'[A-Za-zÀ-ÿ]+',txt(s)) if w.lower() not in {'of','the','and','de','da','do','das','dos','e','for'}]
    return ''.join(w[0] for w in words).lower() if len(words)>=2 else ''

def punct(s):
    s=(s or '').strip(); return s if not s or s.endswith(('.', '!', '?')) else s+'.'
def em(s): return '<em>'+html.escape(s,quote=False)+'</em>'
def esc(s): return html.escape(s,quote=False)

def year_of(f):
    if f.get('year'): return f['year']
    m=re.search(r'\b(?:19|20)\d{2}\b',f.get('date',''))
    return m.group(0) if m else 's.d.'

def format_abnt(key,e):
    f={k:txt(v) for k,v in e.fields.items()}; typ=e.type.lower(); year=year_of(f)
    au=author_string(e) or txt(f.get('organization') or f.get('institution') or f.get('publisher') or '')
    title=f.get('title','Sem título'); doi=f.get('doi','').replace('https://doi.org/','').replace('http://doi.org/','').strip(); url=f.get('url','').strip()
    parts=[]
    if au: parts.append(punct(esc(au)))
    if typ=='article':
        parts.append(punct(esc(title)))
        if f.get('journal'): parts.append(em(f['journal'])+',')
        tail=[]
        if f.get('volume'): tail.append('v. '+esc(f['volume']))
        if f.get('number'): tail.append('n. '+esc(f['number']))
        if f.get('pages'): tail.append('p. '+esc(f['pages'].replace('--','-')))
        tail.append(esc(year)); parts.append(', '.join(tail)+'.')
    elif typ in {'book','manual','proceedings'}:
        parts.append(em(title)+'.')
        if f.get('edition'): parts.append(esc(f['edition'])+' ed.')
        place=f.get('address') or f.get('location') or ''; pub=f.get('publisher') or f.get('institution') or ''
        if place and pub: parts.append(esc(place)+': '+esc(pub)+', '+esc(year)+'.')
        elif pub: parts.append(esc(pub)+', '+esc(year)+'.')
        else: parts.append(esc(year)+'.')
    elif typ in {'inbook','incollection','inproceedings'}:
        parts.append(punct(esc(title))); ed=author_string(e,'editor'); book=f.get('booktitle',''); mid='In: '
        if ed: mid+=esc(ed)+' (org.). '
        if book: mid+=em(book)+'.'
        if mid!='In: ': parts.append(mid)
        place=f.get('address') or f.get('location') or ''; pub=f.get('publisher',''); loc=''
        if place and pub: loc=esc(place)+': '+esc(pub)+', '
        elif pub: loc=esc(pub)+', '
        loc+=esc(year)+'.'
        if f.get('pages'): loc+=' p. '+esc(f['pages'].replace('--','-'))+'.'
        parts.append(loc)
    elif typ in {'phdthesis','mastersthesis'}:
        parts.append(em(title)+'.'); school=f.get('school') or f.get('institution') or ''; kind='Tese (Doutorado)' if typ=='phdthesis' else 'Dissertação (Mestrado)'
        parts.append(kind+((' – '+esc(school)) if school else '')+', '+esc(year)+'.')
    else:
        parts.append(em(title)+'.'); org=f.get('institution') or f.get('organization') or f.get('publisher') or ''
        parts.append((esc(org)+', ' if org else '')+esc(year)+'.')
    if doi: parts.append('DOI: '+esc(doi)+'.')
    elif url: parts.append('Disponível em: &lt;'+esc(url)+'&gt;. Acesso em: '+ACCESS+'.')
    return ' '.join(p for p in parts if p).replace('..','.').strip()

records=[]
for key,e in bib.entries.items():
    year=txt(e.fields.get('year','')); corpus=' '.join([key,author_string(e),txt(e.fields.get('title','')),txt(e.fields.get('organization','')),txt(e.fields.get('institution','')),txt(e.fields.get('publisher',''))])
    acros={acronym(author_string(e)),acronym(e.fields.get('organization','')),acronym(e.fields.get('institution',''))}
    records.append({'key':key,'year':year,'surnames':surnames(e),'corpus':norm(corpus),'acros':{a for a in acros if a},'formatted':format_abnt(key,e)})

refs=[]; chapter_counts={}
for d in chapters:
    soup=BeautifulSoup(d.get('html',''),'html.parser'); found=[]
    for h in soup.find_all(['h2','h3']):
        if not norm(h.get_text(' ',strip=True)).startswith('referencias'): continue
        node=h.find_next_sibling()
        while node and getattr(node,'name',None) not in {'ul','ol'}:
            if getattr(node,'name',None) in {'h2','h3'}: node=None; break
            node=node.find_next_sibling()
        if node:
            found += [li.get_text(' ',strip=True) for li in node.find_all('li',recursive=False) if li.get_text(' ',strip=True)]
    chapter_counts[d['num']]=len(found); refs.extend((d['num'],d.get('title',''),s) for s in found)

stop={'e','and','et','al','de','da','do','das','dos','the','of','for','in'}
def match_ref(short):
    n=norm(short); ym=re.search(r'\b((?:19|20)\d{2})([a-z]?)\b',n); year=ym.group(1) if ym else ''; stem=n[:ym.start()] if ym else n
    words=[w for w in stem.split() if w not in stop and not w.isdigit()]
    if 'et al' in n and words: words=words[:1]
    candidates=[r for r in records if not year or r['year'].startswith(year)]; scored=[]
    for r in candidates:
        score=0
        if words:
            first=words[0]
            if first in r['surnames']: score+=12
            if first in r['acros']: score+=12
            if first in r['corpus'].split(): score+=5
            elif first in r['corpus']: score+=2
            for w in words[1:]:
                if w in r['surnames']: score+=6
                elif w in r['corpus'].split(): score+=3
                elif w in r['corpus']: score+=1
        if year and r['year'].startswith(year): score+=4
        scored.append((score,r))
    scored.sort(key=lambda x:x[0],reverse=True)
    if not scored or scored[0][0]<6: return None,scored[:5]
    top=[x for x in scored if x[0]==scored[0][0]]
    if len(top)>1:
        def cover(r): return sum(1 for w in words if w in r['surnames'] or w in r['corpus'].split())
        cov=sorted([(cover(r),r) for _,r in top],key=lambda x:x[0],reverse=True)
        if len(cov)>1 and cov[0][0]==cov[1][0]: return None,scored[:5]
        return cov[0][1],scored[:5]
    return scored[0][1],scored[:5]

mapping={}; unresolved=[]
for cap,title,short in refs:
    k=js_ref_key(short)
    if k in mapping: continue
    rec,choices=match_ref(short)
    if rec: mapping[k]=rec['formatted']
    else: unresolved.append((cap,title,short,[(s,r['key'],r['year']) for s,r in choices]))

index=(ROOT/'index.html').read_text(encoding='utf-8'); lines=['const ABNT_REFS={']
for k in sorted(mapping): lines.append('  '+json.dumps(k,ensure_ascii=False)+':'+json.dumps(mapping[k],ensure_ascii=False).replace('</','<\\/')+',')
if len(lines)>1: lines[-1]=lines[-1].rstrip(',')
lines.append('};'); js='\n'.join(lines)
index2,repl=re.subn(r'const ABNT_REFS=\{.*?\};',lambda m:js,index,count=1,flags=re.S)
if repl!=1: raise SystemExit('ABNT_REFS não localizado no index.html')
(ROOT/'index.html').write_text(index2,encoding='utf-8')

report=['# Auditoria — referências ABNT por capítulo','',f'- Capítulos verificados: {len(chapters)}',f'- Itens bibliográficos encontrados: {len(refs)}',f'- Referências distintas resolvidas: {len(mapping)}',f'- Itens não resolvidos: {len(unresolved)}',f'- Base bibliográfica: `{bib_path}`','','## Contagem por capítulo','']
for n in range(1,29): report.append(f'- Capítulo {n}: {chapter_counts.get(n,0)} referência(s)')
report += ['']
if unresolved:
    report += ['## Não resolvidas','']
    for cap,title,short,choices in unresolved:
        report += [f'### Capítulo {cap} — {title}',f'- Original: `{short}`','- Candidatas: '+('; '.join(f'{key} ({year}, score {score})' for score,key,year in choices) if choices else 'nenhuma'),'']
else:
    report += ['## Resultado','','Todas as referências abreviadas localizadas ao final dos capítulos foram resolvidas para entradas completas da base bibliográfica e formatadas para apresentação conforme ABNT NBR 6023:2018.']
(ROOT/'ABNT_REFERENCES_AUDIT.md').write_text('\n'.join(report)+'\n',encoding='utf-8')
(ROOT/'abnt-references-map.json').write_text(json.dumps(mapping,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('\n'.join(report[:12]))
