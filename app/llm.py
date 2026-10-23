import json,os,urllib.request,re,unicodedata
from pydantic import BaseModel,Field,ValidationError
class TestCase(BaseModel):
 title:str=Field(min_length=3,max_length=180)
 preconditions:list[str]=Field(min_length=1)
 steps:list[str]=Field(min_length=2)
 expected_result:str=Field(min_length=10)
 source_evidence:str=Field(min_length=10,max_length=800)
 source_node_ids:list[int]=Field(min_length=1)
 risk:str=Field(pattern='^(low|medium|high)$')
class Cases(BaseModel): cases:list[TestCase]=Field(min_length=3,max_length=5)
GROQ_CASES_SCHEMA={
 'type':'object',
 'properties':{'cases':{'type':'array','minItems':3,'maxItems':5,'items':{
  'type':'object','properties':{
   'title':{'type':'string'},
   'preconditions':{'type':'array','items':{'type':'string'},'minItems':1},
   'steps':{'type':'array','items':{'type':'string'},'minItems':2},
   'expected_result':{'type':'string'},
   'source_evidence':{'type':'string'},
   'source_node_ids':{'type':'array','items':{'type':'integer'},'minItems':1},
   'risk':{'type':'string','enum':['low','medium','high']},
  },
  'required':['title','preconditions','steps','expected_result','source_evidence','source_node_ids','risk'],
  'additionalProperties':False,
 }}},
 'required':['cases'],'additionalProperties':False,
}
def _normalise_quote(value):
 value=unicodedata.normalize('NFKC',value).casefold()
 return re.sub(r'\s+',' ',value).strip()

def _asserts_outcome(step,evidence):
 outcome_patterns=(r'\b(?:indicates?|indicated)\b',r'\b(?:displays?|displayed)\b',r'\b(?:shows?|showed)\b',r'\b(?:appears?|appeared)\b',r'\b(?:clears?|cleared)\b',r'\b(?:triggers?|triggered)\b',r'\b(?:aborts?|aborted)\b',r'\b(?:deflates?|deflated)\b',r'\b(?:prompts?|prompted)\b',r'\b(?:recommends?|recommended)\b',r'\bresults?\s+in\b',r'\bpowers?\s+off\b')
 output_concepts=(r'\bindicat\w*\b',r'\bdispla\w*\b',r'\bscreens?\b',r'\bicons?\b',r'\balerts?\b',r'\bwarnings?\b',r'\bprompts?\b',r'\bmessages?\b')
 unsupported_concept=any(re.search(pattern,step,re.I) and not re.search(pattern,evidence,re.I) for pattern in output_concepts)
 if unsupported_concept:return True
 # A neutral observation question is safe when it targets an output named in
 # the evidence (for example, checking whether the documented icon appears).
 neutral_question=re.search(r'\b(?:observe|check|verify|record|note|monitor)\b.{0,100}\b(?:whether|if)\b',step,re.I)
 if neutral_question and any(re.search(pattern,step,re.I) and re.search(pattern,evidence,re.I) for pattern in output_concepts):return False
 return any(re.search(pattern,step,re.I) and not re.search(pattern,evidence,re.I) for pattern in outcome_patterns)

def validate(payload,node_ids,source_text='',source_by_node=None):
 obj=Cases.model_validate(payload)
 allowed=set(node_ids)
 if any(not set(c.source_node_ids)<=allowed for c in obj.cases):raise ValueError('case cites a node outside selection')
 for case in obj.cases:
  cited_text='\n'.join((source_by_node or {}).get(node_id,source_text) for node_id in case.source_node_ids)
  cited_source=_normalise_quote(cited_text)
  evidence=_normalise_quote(case.source_evidence)
  if not evidence or evidence not in cited_source:
   raise ValueError('source_evidence must be an exact quote from one of the cited source nodes')
  if _normalise_quote(case.expected_result)!=evidence:
   raise ValueError('expected_result must exactly match its source_evidence quote; paraphrased outcomes are not accepted')
  source_numbers=set(re.findall(r'(?<![A-Za-z])\d+(?:\.\d+)?%?',cited_source))
  case_text=' '.join([case.title,*case.preconditions,*case.steps])
  invented=sorted(set(re.findall(r'(?<![A-Za-z])\d+(?:\.\d+)?%?',_normalise_quote(case_text)))-source_numbers)
  if invented:
   raise ValueError('case introduces numeric values absent from selected source text: '+', '.join(invented))
  if any(_asserts_outcome(step,case.source_evidence) for step in case.steps):
   raise ValueError('steps contain an outcome or device-output concept absent from the cited source evidence; use neutral actions or observations')
 return obj
def _call(url,key,model,text,correction=None):
 system=('Generate 3-5 concrete, repeatable QA test ideas grounded only in supplied text. '
 'Each case must have title, preconditions, at least two executable steps, expected_result, '
 'source_evidence, source_node_ids, and risk. source_evidence must be copied verbatim from one '
 'complete requirement sentence or table row in the selected text. Provide at least two neutral '
 'action/observation steps in every case. expected_result MUST be exactly '
 'the same quote as source_evidence; do not paraphrase it or add behavior, implications, thresholds, '
 'or assumptions. Do not introduce numeric values absent from the selected text. Write steps as neutral '
 'actions or observations (for example: perform, record, measure, observe, compare); do not state '
 'predicted device behavior in steps. '
 'Use only node IDs supplied in the text. If evidence is insufficient for a distinct claim, vary the '
 'test setup while preserving the same explicitly quoted expected result.')
 user='Source nodes and exact text:\n'+text
 source_numbers=sorted(set(re.findall(r'(?<![A-Za-z])\d+(?:\.\d+)?%?',_normalise_quote(text))))
 user+='\nNumeric tokens present in the supplied text (do not calculate or derive other values): '+', '.join(source_numbers)
 if correction:user+='\nYour previous response failed validation. Correct these issues: '+correction
 data=json.dumps({'model':model,'temperature':0,'max_completion_tokens':2048,'response_format':{'type':'json_schema','json_schema':{'name':'ct200_qa_cases','strict':True,'schema':GROQ_CASES_SCHEMA}},'messages':[{'role':'system','content':system},{'role':'user','content':user}]}).encode()
 req=urllib.request.Request(url,data,{'Authorization':'Bearer '+key,'Content-Type':'application/json','Accept':'application/json','User-Agent':'tri9t-ct200/1.0'})
 with urllib.request.urlopen(req,timeout=45) as res:raw=json.loads(res.read())
 return raw['choices'][0]['message']['content']

def generate(text,node_ids,source_by_node=None):
 """Try primary twice, then one independently configured fallback provider."""
 providers=[]
 primary_key=os.getenv('LLM_API_KEY')
 if primary_key:
  providers.append(('primary',os.getenv('LLM_BASE_URL','https://api.groq.com/openai/v1/chat/completions'),primary_key,os.getenv('LLM_MODEL','openai/gpt-oss-120b'),2))
 fallback_key=os.getenv('LLM_FALLBACK_API_KEY')
 if fallback_key:
  providers.append(('fallback',os.getenv('LLM_FALLBACK_BASE_URL','https://api.groq.com/openai/v1/chat/completions'),fallback_key,os.getenv('LLM_FALLBACK_MODEL','openai/gpt-oss-120b'),1))
 if not providers:raise RuntimeError('Configure LLM_API_KEY or LLM_FALLBACK_API_KEY')
 errors=[];attempts=0
 for provider,url,key,model,max_attempts in providers:
  correction=None
  for _ in range(max_attempts):
   attempts+=1
   raw=None
   try:
    raw=_call(url,key,model,text,correction)
    cases=validate(json.loads(raw),node_ids,text,source_by_node)
    return cases,model,attempts,provider
   except Exception as e:
    # Never return or persist partial/unvalidated provider content.
    correction=f'{type(e).__name__}: {e}'
    if raw is not None:correction+='\nPrevious invalid response; revise it rather than repeating the issue:\n'+raw[:12000]
    errors.append(f'{provider}/{model}: {correction}')
 raise ValueError('LLM output failed validation or provider request after bounded retry/fallback: '+' | '.join(errors))
