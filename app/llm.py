import json,os,urllib.request
from pydantic import BaseModel,Field,ValidationError
class TestCase(BaseModel):
 title:str=Field(min_length=3,max_length=180)
 preconditions:list[str]=Field(min_length=1)
 steps:list[str]=Field(min_length=2)
 expected_result:str=Field(min_length=10)
 source_node_ids:list[int]=Field(min_length=1)
 risk:str=Field(pattern='^(low|medium|high)$')
class Cases(BaseModel): cases:list[TestCase]=Field(min_length=3,max_length=5)
def validate(payload,node_ids):
 obj=Cases.model_validate(payload)
 if any(not set(c.source_node_ids)<=set(node_ids) for c in obj.cases):raise ValueError('case cites a node outside selection')
 return obj
def _call(url,key,model,text,correction=None):
 system='Generate 3-5 concrete, repeatable QA tests grounded only in supplied text. Return JSON object {"cases":[{title,preconditions,steps,expected_result,source_node_ids,risk}]}. Do not invent thresholds. If text is insufficient, use explicit observable expected behavior only.'
 user='Source nodes and exact text:\n'+text
 if correction:user+='\nYour previous response failed validation. Correct these issues: '+correction
 data=json.dumps({'model':model,'temperature':0,'response_format':{'type':'json_object'},'messages':[{'role':'system','content':system},{'role':'user','content':user}]}).encode()
 req=urllib.request.Request(url,data,{'Authorization':'Bearer '+key,'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=45) as res:raw=json.loads(res.read())
 return raw['choices'][0]['message']['content']

def generate(text,node_ids):
 """Try primary twice, then one independently configured fallback provider."""
 providers=[]
 primary_key=os.getenv('LLM_API_KEY')
 if primary_key:
  providers.append(('primary',os.getenv('LLM_BASE_URL','https://api.groq.com/openai/v1/chat/completions'),primary_key,os.getenv('LLM_MODEL','llama-3.3-70b-versatile'),2))
 fallback_key=os.getenv('LLM_FALLBACK_API_KEY')
 if fallback_key:
  providers.append(('fallback',os.getenv('LLM_FALLBACK_BASE_URL','https://api.groq.com/openai/v1/chat/completions'),fallback_key,os.getenv('LLM_FALLBACK_MODEL','llama-3.3-70b-versatile'),1))
 if not providers:raise RuntimeError('Configure LLM_API_KEY or LLM_FALLBACK_API_KEY')
 errors=[];attempts=0
 for provider,url,key,model,max_attempts in providers:
  correction=None
  for _ in range(max_attempts):
   attempts+=1
   try:
    raw=_call(url,key,model,text,correction)
    cases=validate(json.loads(raw),node_ids)
    return cases,model,attempts,provider
   except Exception as e:
    # Never return or persist partial/unvalidated provider content.
    correction=f'{type(e).__name__}: {e}'
    errors.append(f'{provider}/{model}: {correction}')
 raise ValueError('LLM output failed validation or provider request after bounded retry/fallback: '+' | '.join(errors))
