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
def generate(text,node_ids):
 url=os.getenv('LLM_BASE_URL','https://api.groq.com/openai/v1/chat/completions');key=os.getenv('LLM_API_KEY');model=os.getenv('LLM_MODEL','llama-3.3-70b-versatile')
 if not key:raise RuntimeError('LLM_API_KEY is not configured')
 system='Generate 3-5 concrete, repeatable QA tests grounded only in supplied text. Return JSON object {"cases":[{title,preconditions,steps,expected_result,source_node_ids,risk}]}. Do not invent thresholds. If text is insufficient, use explicit observable expected behavior only.'
 errors=[]
 for attempt in range(2):
  user='Source nodes and exact text:\n'+text
  if errors:user+='\nCorrect these validation errors: '+ '; '.join(errors)
  data=json.dumps({'model':model,'temperature':0,'response_format':{'type':'json_object'},'messages':[{'role':'system','content':system},{'role':'user','content':user}]}).encode()
  req=urllib.request.Request(url,data,{'Authorization':'Bearer '+key,'Content-Type':'application/json'})
  with urllib.request.urlopen(req,timeout=45) as res:raw=json.loads(res.read())
  try:return validate(json.loads(raw['choices'][0]['message']['content']),node_ids),model,attempt+1
  except (ValidationError,ValueError,KeyError,json.JSONDecodeError) as e:errors=[str(e)]
 raise ValueError('LLM output failed validation after bounded retry: '+errors[-1])
