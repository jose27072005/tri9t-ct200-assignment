"""CT-200 focused PDF text parser; OCR is an opt-in fallback for image-only pages."""
from dataclasses import dataclass,field
import hashlib,re
from pathlib import Path
@dataclass
class ParsedNode:
    heading:str
    level:int
    body:str=''
    children:list['ParsedNode']=field(default_factory=list)
def sha(text:str)->str:return hashlib.sha256(text.encode()).hexdigest()
def norm(text):return re.sub(r'\s+',' ',text).strip().casefold()
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
def parse_text(text:str)->list[ParsedNode]:
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
   import fitz,pytesseract,io
   from PIL import Image
   doc=fitz.open(str(path))
   for i in empty:pages[i-1]=pytesseract.image_to_string(Image.open(io.BytesIO(doc[i-1].get_pixmap(matrix=fitz.Matrix(2,2)).tobytes('png'))))
  except Exception as e:raise ValueError(f'OCR fallback unavailable or failed for pages {empty}: {e}')
 if empty and not ocr:raise ValueError(f'Image-only pages require OCR mode: {empty}')
 text='\n'.join(pages)
 if not text.strip():raise ValueError('PDF yielded no text')
 return parse_text(text),text
def flatten(nodes,parent_path=''):
 out=[]
 for i,n in enumerate(nodes):
  path=f'{parent_path}/{i}:{norm(n.heading)}';out.append((n,path));out.extend(flatten(n.children,path))
 return out
