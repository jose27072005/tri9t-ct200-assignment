"""Durable JSON document store for generated payloads; each write is atomic."""
import json,os,tempfile
from pathlib import Path
STORE=Path(os.getenv('OUTPUT_STORE','./generated_outputs.json'))
def read_all():
 if not STORE.exists():return []
 return json.loads(STORE.read_text())
def put(record):
 STORE.parent.mkdir(parents=True,exist_ok=True);items=read_all();items.append(record)
 fd,tmp=tempfile.mkstemp(dir=STORE.parent,prefix='.outputs-')
 try:
  with os.fdopen(fd,'w') as f:json.dump(items,f,indent=2)
  os.replace(tmp,STORE)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)
 return record
def get(generation_id=None):return [x for x in read_all() if generation_id is None or x['id']==generation_id]
