import itertools
import json
from pathlib import Path
import random

ROOT=Path(__file__).resolve().parent
MODES=['query','tenant','context']
SCENARIOS=['repeat','denied','cross_tenant','same_tenant_scope','revoked','source_update']
FIXTURES=[]
for i,text in enumerate(['plain','with space','café','quote "','line\nbreak','path/a','braces {}','zero 0']):
    query='lookup '+text
    doc_a={'id':f'doc-A-{i}','tenant':'alpha','query':query,'version':1,'value':f'SYNTHETIC_A_{i}_v1'}
    doc_b={'id':f'doc-B-{i}','tenant':'beta','query':query,'version':1,'value':f'SYNTHETIC_B_{i}_v1'}
    FIXTURES.append({'id':f'f{i}','query':query,'documents':[doc_a,doc_b],
        'grants':{'owner-A':[doc_a['id']],'peer-A':[doc_a['id']],'reader-A':[],'owner-B':[doc_b['id']]},'updated_value':f'SYNTHETIC_A_{i}_v2'})
SCHEDULE=[dict(id=f['id']+'-'+m+'-'+s,fixture_id=f['id'],mode=m,scenario=s) for f,m,s in itertools.product(FIXTURES,MODES,SCENARIOS)]
random.Random(20261118).shuffle(SCHEDULE)
if __name__=='__main__':
    for name,value in [('fixtures.json',FIXTURES),('schedule.json',SCHEDULE)]:
        (ROOT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
