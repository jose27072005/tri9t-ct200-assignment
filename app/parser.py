"""CT-200 focused PDF text parser; OCR is an opt-in fallback for image-only pages."""
from dataclasses import dataclass,field
import hashlib,re,unicodedata
from pathlib import Path
@dataclass
class ParsedNode:
    heading:str
    level:int
    body:str=''
    children:list['ParsedNode']=field(default_factory=list)
def sha(text:str)->str:return hashlib.sha256(text.encode()).hexdigest()
def norm(text):return re.sub(r'\s+',' ',unicodedata.normalize('NFKC',text)).strip().casefold()
NUM=re.compile(r'^\s*(\d+(?:\.\d+){0,5})\.?\s+(.+?)\s*$')
LETTER=re.compile(r'^\s*([A-Z])\.\s+(.+?)\s*$')
ROMAN=re.compile(r'^\s*((?:I|II|III|IV|V|VI|VII|VIII|IX|X))\.\s+(.+?)\s*$')
ALLCAPS=re.compile(r'^[A-Z][A-Z0-9 /&(),:-]{2,80}$')
def heading_level(line):
 m=NUM.match(line)
 if m:return min(m.group(1).count('.')+1,6),m.group(2).strip()
 m=LETTER.match(line)
 if m:return 2,m.group(2).strip()
 m=ROMAN.match(line)
 if m:return 3,m.group(2).strip()
 if ALLCAPS.match(line.strip()) and len(line.strip())<=80:return 1,line.strip().title()
 return None
def parse_text(text:str,heading_hints:set[str]|None=None)->list[ParsedNode]:
 roots=[];stack=[];current=None;body=[];preamble=[]
 def flush():
  nonlocal body
  if current is not None:current.body='\n'.join(body).strip()
  elif body:preamble.extend(body)
  body=[]
 for raw in text.replace('\r','').splitlines():
  line=re.sub(r'\s+',' ',raw).strip()
  if not line or re.fullmatch(r'\d{1,4}',line) or ('CardioTrack' in line and len(line)<25):continue
  h=heading_level(line)
  if h and heading_hints is not None and norm(line) not in heading_hints:h=None
  if h:
   flush();level,title=h;node=ParsedNode(title,level)
   while stack and stack[-1].level>=level:stack.pop()
   (stack[-1].children if stack else roots).append(node);stack.append(node);current=node
  else:body.append(line)
 flush()
 if preamble:roots.insert(0,ParsedNode('Document introduction',1,'\n'.join(preamble)))
 if not roots and text.strip():roots=[ParsedNode('Document',1,text.strip())]
 return roots
def extract_pdf(path:str|Path,ocr:bool=False):
 from pypdf import PdfReader
 reader=PdfReader(str(path));pages=[];empty=[]
 for i,p in enumerate(reader.pages):
  t=(p.extract_text() or '').strip();pages.append(t)
  if not t:empty.append(i+1)
 if empty and ocr:
  try:
   import pymupdf,pytesseract,io
   from PIL import Image
   doc=pymupdf.open(str(path))
   for i in empty:pages[i-1]=pytesseract.image_to_string(Image.open(io.BytesIO(doc[i-1].get_pixmap(matrix=pymupdf.Matrix(2,2)).tobytes('png'))))
  except Exception as e:raise ValueError(f'OCR fallback unavailable or failed for pages {empty}: {e}')
 if empty and not ocr:raise ValueError(f'Image-only pages require OCR mode: {empty}')
 text='\n'.join(pages)
 if not text.strip():raise ValueError('PDF yielded no text')
 # Font weight disambiguates real section headings from numbered result lists.
 hints=None if empty else set()
 try:
  import pymupdf
  if hints is None: raise RuntimeError("OCR text has no embedded font metadata")
  doc=pymupdf.open(str(path))
  for page in doc:
   for block in page.get_text('dict').get('blocks',[]):
    for line in block.get('lines',[]):
     spans=line.get('spans',[])
     value=' '.join(span.get('text','') for span in spans).strip()
     if value and any(('bold' in span.get('font','').casefold()) or (span.get('flags',0)&16) for span in spans):hints.add(norm(value))
 except RuntimeError:
  pass
 except Exception:
  hints=None
 return parse_text(text,hints),text

def extract_tables(path:str|Path)->list[dict]:
 """Extract real CT-200 grid tables, ignoring line fragments from table borders."""
 import pymupdf
 doc=pymupdf.open(str(path));found=[]
 for page_index,page in enumerate(doc):
  headings=[]
  for block in page.get_text('dict').get('blocks',[]):
   for line in block.get('lines',[]):
    spans=line.get('spans',[]);value=' '.join(s.get('text','') for s in spans).strip()
    if value and any(('bold' in s.get('font','').casefold()) or (s.get('flags',0)&16) for s in spans):
     parsed=heading_level(value)
     if parsed:headings.append((min(s['bbox'][1] for s in spans),parsed[1]))
  try:candidates=page.find_tables().tables
  except Exception as e:raise ValueError(f'Table detection failed on page {page_index+1}: {e}')
  page_seen=set()
  for table in candidates:
   rows=[[str(cell or '').strip() for cell in row] for row in table.extract()]
   rows=[row for row in rows if any(row)]
   # PyMuPDF can report each internal ruling as a tiny table. Keep coherent grids;
   # the CT-200 manual's actual tables have at least three rows and two columns.
   width=max((len(row) for row in rows),default=0)
   if len(rows)<3 or width<2 or sum(bool(cell) for row in rows for cell in row)<6:continue
   key=tuple(tuple(row) for row in rows)
   if key in page_seen:continue
   page_seen.add(key)
   y0=float(table.bbox[1]);before=[h for y,h in headings if y<=y0]
   found.append({'page_number':page_index+1,'heading_context':before[-1] if before else None,
    'caption':None,'bbox':[round(float(x),2) for x in table.bbox],
    'rows':rows,'row_count':len(rows),'column_count':width})
 doc.close()
 # Border rules inside a detected grid can yield a second, smaller table object.
 # Discard a candidate almost wholly enclosed by a larger table on the same page.
 filtered=[]
 for candidate in found:
  x0,y0,x1,y1=candidate['bbox'];area=max(0,x1-x0)*max(0,y1-y0);nested=False
  for other in found:
   if other is candidate or other['page_number']!=candidate['page_number']:continue
   a0,b0,a1,b1=other['bbox'];other_area=max(0,a1-a0)*max(0,b1-b0)
   overlap=max(0,min(x1,a1)-max(x0,a0))*max(0,min(y1,b1)-max(y0,b0))
   if other_area>area*1.2 and area and overlap/area>=.9:nested=True;break
  if not nested:filtered.append(candidate)
 return filtered

def flatten(nodes,parent_path=''):
 out=[]
 for i,n in enumerate(nodes):
  path=f'{parent_path}/{i}:{norm(n.heading)}';out.append((n,path));out.extend(flatten(n.children,path))
 return out
