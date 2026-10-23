from fastapi import FastAPI,HTTPException,Depends,UploadFile,File
from pydantic import BaseModel,Field
from sqlalchemy.orm import Session
from sqlalchemy import select
from contextlib import asynccontextmanager
from pathlib import Path
import hashlib,uuid,difflib,os
from .db import SessionLocal,init_db
from .models import DocumentVersion,DocumentNode,Selection,SelectionItem
from .parser import extract_pdf,flatten,sha,norm
from . import store,llm
@asynccontextmanager
async def lifespan(_app):
 init_db()
 yield
app=FastAPI(title='Tri9T CT-200 Traceability API',version='1.0.0',lifespan=lifespan)
def dbdep():
 db=SessionLocal()
 try:yield db
 finally:db.close()
class Ingest(BaseModel):document_key:str='ct-200';version:str;path:str;ocr:bool=False
class SelectionIn(BaseModel):name:str=Field(min_length=1,max_length=250);document_key:str='ct-200';version:str|None=None;node_ids:list[int]=Field(min_length=1)
class GenerateIn(BaseModel):selection_id:int

def version_for(db,key,version):
 q=select(DocumentVersion).where(DocumentVersion.document_key==key)
 if version:q=q.where(DocumentVersion.version==version)
 return db.scalars(q.order_by(DocumentVersion.id.desc())).first()
def tree_json(n,full=False):
 d={'id':n.id,'logical_id':n.logical_id,'heading':n.heading,'level':n.level,'parent_id':n.parent_id,'content_hash':n.content_hash,'changed':n.changed,'change_kind':n.change_kind,'children':[tree_json(c,full) for c in n.children]}
 if full:d['text']=n.body
 return d
def subtree_text(n):
 pieces=[n.heading]
 if n.body.strip():pieces.append(n.body.strip())
 for child in n.children:
  pieces.append(subtree_text(child))
 return '\n'.join(pieces)
def subtree_nodes(n):
 nodes=[n]
 for child in n.children:nodes.extend(subtree_nodes(child))
 return nodes
def subtree_prompt(n):
 lines=[f'[{n.id}] {n.heading}']
 if n.body.strip():lines.append(n.body.strip())
 for child in n.children:lines.append(subtree_prompt(child))
 return '\n'.join(lines)
@app.get('/health')
def health():return {'status':'ok'}
@app.post('/ingest')
def ingest(inp:Ingest,db:Session=Depends(dbdep)):
 p=Path(inp.path)
 if not p.is_file():raise HTTPException(404,'PDF path not found')
 try:parsed,raw=extract_pdf(p,inp.ocr)
 except Exception as e:raise HTTPException(422,str(e))
 if db.scalar(select(DocumentVersion).where(DocumentVersion.document_key==inp.document_key,DocumentVersion.version==inp.version)):raise HTTPException(409,'Version already exists; use a new version label')
 previous=version_for(db,inp.document_key,None)
 old_by_path={}
 if previous:
  for n in db.scalars(select(DocumentNode).where(DocumentNode.document_version_id==previous.id)):
   # Reconstruct path from ancestor ordinals/headings so repeats keep sibling occurrence identity.
   parts=[];cur=n
   while cur:
    parts.append(f'{cur.ordinal}:{norm(cur.heading)}');cur=cur.parent
   old_by_path['/'.join(reversed(parts))]=n
 doc=DocumentVersion(document_key=inp.document_key,version=inp.version,source_name=p.name,source_sha256=hashlib.sha256(p.read_bytes()).hexdigest());db.add(doc);db.flush()
 def save(nodes,parent,path=''):
  for i,node in enumerate(nodes):
   segment=f'{i}:{norm(node.heading)}'
   current=f'{path}/{segment}' if path else segment
   content_hash=sha(node.heading+'\n'+node.body)
   old=old_by_path.get(current);logical=old.logical_id if old else str(uuid.uuid5(uuid.NAMESPACE_URL,inp.document_key+current))
   changed=bool(old and old.content_hash!=content_hash)
   row=DocumentNode(logical_id=logical,document_version_id=doc.id,parent_id=parent,ordinal=i,heading=node.heading,level=node.level,body=node.body,content_hash=content_hash,changed=changed,change_kind='content' if changed else ('new' if previous and not old else None));db.add(row);db.flush()
   save(node.children,row.id,current)
 save(parsed,None);db.commit()
 return {'document_key':inp.document_key,'version':inp.version,'source_sha256':doc.source_sha256,'node_count':db.scalar(select(DocumentNode).where(DocumentNode.document_version_id==doc.id).count()) if False else len(flatten(parsed))}
@app.post('/ingest-upload')
def ingest_upload(document_key:str,version:str,file:UploadFile=File(...),ocr:bool=False,db:Session=Depends(dbdep)):
 target=Path('data')/f'{document_key}-{version}-{file.filename}';target.parent.mkdir(exist_ok=True)
 target.write_bytes(file.file.read());return ingest(Ingest(document_key=document_key,version=version,path=str(target),ocr=ocr),db)
@app.get('/documents/{key}/versions')
def versions(key:str,db:Session=Depends(dbdep)):
 return [{'version':v.version,'source_name':v.source_name,'source_sha256':v.source_sha256} for v in db.scalars(select(DocumentVersion).where(DocumentVersion.document_key==key).order_by(DocumentVersion.id))]
@app.get('/documents/{key}/nodes')
def roots(key:str,version:str|None=None,db:Session=Depends(dbdep)):
 v=version_for(db,key,version)
 if not v:raise HTTPException(404,'document version not found')
 return [tree_json(n) for n in db.scalars(select(DocumentNode).where(DocumentNode.document_version_id==v.id,DocumentNode.parent_id.is_(None)).order_by(DocumentNode.ordinal))]
@app.get('/nodes/{node_id}')
def node(node_id:int,db:Session=Depends(dbdep)):
 n=db.get(DocumentNode,node_id)
 if not n:raise HTTPException(404,'node not found')
 return tree_json(n,True)
@app.get('/documents/{key}/search')
def search(key:str,q:str,version:str|None=None,db:Session=Depends(dbdep)):
 v=version_for(db,key,version)
 if not v:raise HTTPException(404,'document version not found')
 qn=q.casefold();return [tree_json(n,True) for n in db.scalars(select(DocumentNode).where(DocumentNode.document_version_id==v.id)) if qn in n.heading.casefold() or qn in n.body.casefold()]
@app.get('/nodes/{node_id}/diff')
def diff(node_id:int,db:Session=Depends(dbdep)):
 n=db.get(DocumentNode,node_id)
 if not n:raise HTTPException(404,'node not found')
 peers=list(db.scalars(select(DocumentNode).where(DocumentNode.logical_id==n.logical_id).order_by(DocumentNode.document_version_id)))
 return {'logical_id':n.logical_id,'versions':[{'version':x.document.version,'node_id':x.id,'content_hash':x.content_hash,'changed':x.changed,'change_kind':x.change_kind} for x in peers],'diff':list(difflib.unified_diff(peers[-2].body.splitlines(),peers[-1].body.splitlines(),fromfile=peers[-2].document.version,tofile=peers[-1].document.version)) if len(peers)>1 else []}
@app.post('/selections')
def create_selection(inp:SelectionIn,db:Session=Depends(dbdep)):
 v=version_for(db,inp.document_key,inp.version)
 if not v:raise HTTPException(404,'document version not found')
 rows=list(db.scalars(select(DocumentNode).where(DocumentNode.document_version_id==v.id,DocumentNode.id.in_(inp.node_ids))))
 if len(rows)!=len(set(inp.node_ids)):raise HTTPException(422,'one or more node IDs are invalid for that version')
 s=Selection(name=inp.name,document_key=inp.document_key,document_version_id=v.id);db.add(s);db.flush()
 for n in rows:
  snapshot=subtree_text(n)
  db.add(SelectionItem(selection_id=s.id,node_id=n.id,node_logical_id=n.logical_id,content_hash=sha(snapshot),heading_snapshot=n.heading,text_snapshot=snapshot))
 db.commit();return {'id':s.id,'name':s.name,'version':v.version,'node_ids':inp.node_ids}
@app.get('/selections/{selection_id}')
def get_selection(selection_id:int,db:Session=Depends(dbdep)):
 s=db.get(Selection,selection_id)
 if not s:raise HTTPException(404,'selection not found')
 v=db.get(DocumentVersion,s.document_version_id)
 items=list(db.scalars(select(SelectionItem).where(SelectionItem.selection_id==s.id)))
 return {'id':s.id,'name':s.name,'document_key':s.document_key,'version':v.version,'items':[{'node_id':i.node_id,'logical_id':i.node_logical_id,'heading':i.heading_snapshot,'content_hash':i.content_hash,'text':i.text_snapshot} for i in items]}
def generation_staleness(record,db):
 stale=[];current=version_for(db,record['document_key'],None)
 impacted={}
 for src in record['sources']:
  n=db.scalars(select(DocumentNode).where(DocumentNode.document_version_id==current.id,DocumentNode.logical_id==src['logical_id'])).first() if current else None
  if not n or sha(subtree_text(n))!=src['content_hash']:
   impacted[src['logical_id']]={'logical_id':src['logical_id'],'heading':src['heading'],'current_node_id':n.id if n else None,'changed':True,'reason':'selected subtree changed or disappeared'}
   for member in src.get('included_nodes',[]):
    latest=db.scalars(select(DocumentNode).where(DocumentNode.document_version_id==current.id,DocumentNode.logical_id==member['logical_id'])).first() if current else None
    if not latest or latest.content_hash!=member['content_hash']:
     impacted[member['logical_id']]={'logical_id':member['logical_id'],'heading':member['heading'],'current_node_id':latest.id if latest else None,'changed':True,'reason':'node changed or disappeared'}
 return {'stale':bool(impacted),'current_version':current.version if current else None,'impacted_sources':list(impacted.values())}
@app.post('/generations')
def generate(inp:GenerateIn,db:Session=Depends(dbdep)):
 s=db.get(Selection,inp.selection_id)
 if not s:raise HTTPException(404,'selection not found')
 items=list(db.scalars(select(SelectionItem).where(SelectionItem.selection_id==s.id)))
 selected_nodes=[db.get(DocumentNode,i.node_id) for i in items]
 text='\n\n'.join(subtree_prompt(n) for n in selected_nodes)
 allowed_node_ids=[n.id for root in selected_nodes for n in subtree_nodes(root)]
 try:cases,model,attempts,provider=llm.generate(text,allowed_node_ids)
 except Exception as e:raise HTTPException(502,str(e))
 sources=[]
 for i,selected in zip(items,selected_nodes):
  sources.append({'node_id':i.node_id,'logical_id':i.node_logical_id,'heading':i.heading_snapshot,'content_hash':i.content_hash,'text':i.text_snapshot,'included_nodes':[{'node_id':n.id,'logical_id':n.logical_id,'heading':n.heading,'content_hash':n.content_hash} for n in subtree_nodes(selected)]})
 record={'id':str(uuid.uuid4()),'selection_id':s.id,'selection_name':s.name,'document_key':s.document_key,'source_version':db.get(DocumentVersion,s.document_version_id).version,'created_at':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),'provider':provider,'model':model,'attempts':attempts,'sources':sources,'cases':[c.model_dump() for c in cases.cases]}
 store.put(record);return {**record,**generation_staleness(record,db)}
@app.get('/generations')
def generations(selection_id:int|None=None,node_id:int|None=None,db:Session=Depends(dbdep)):
 records=store.read_all()
 if selection_id is not None:records=[r for r in records if r['selection_id']==selection_id]
 if node_id is not None:
  n=db.get(DocumentNode,node_id)
  if not n:raise HTTPException(404,'node not found')
  records=[r for r in records if any(s['logical_id']==n.logical_id or any(m['logical_id']==n.logical_id for m in s.get('included_nodes',[])) for s in r['sources'])]
 return [{**r,**generation_staleness(r,db)} for r in records]
@app.get('/generations/{generation_id}')
def generation(generation_id:str,db:Session=Depends(dbdep)):
 records=store.get(generation_id)
 if not records:raise HTTPException(404,'generation not found')
 r=records[0];return {**r,**generation_staleness(r,db)}
