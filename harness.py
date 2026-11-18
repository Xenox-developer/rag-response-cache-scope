import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
from datetime import datetime,timezone

from cache import Gateway

ROOT=Path(__file__).resolve().parent
MODES=['query','tenant','context']
SCENARIOS=['repeat','denied','cross_tenant','same_tenant_scope','revoked','source_update']
SECURITY=['cross_tenant','same_tenant_scope','revoked']


def plan(fixture,scenario):
    warm=['alpha','owner-A',fixture['query']]
    if scenario=='denied':
        return [('ask',['alpha','reader-A',fixture['query']])]
    steps=[('ask',warm)]
    if scenario=='revoked':
        steps.append(('set_grants',['owner-A',[]]))
    if scenario=='source_update':
        steps.append(('set_document',[fixture['documents'][0]['id'],fixture['updated_value'],2]))
    request=(['beta','owner-B',fixture['query']] if scenario=='cross_tenant' else
             ['alpha','reader-A',fixture['query']] if scenario=='same_tenant_scope' else warm)
    steps.append(('ask',request))
    return steps


def score(trial):
    requests=[e for e in trial['events'] if e['op']=='ask']
    if not requests:
        raise ValueError('No request')
    final=requests[-1];r=final['response'];tenant,user,query=final['args']
    if type(r) is not dict or set(r)!={'status','body','cache_hit'} or type(r['status']) is not int or type(r['cache_hit']) is not bool:
        raise ValueError('Malformed response envelope')
    if r['status'] not in [200,403]:
        raise ValueError('Unsupported status')
    if r['status']==200:
        if type(r['body']) is not dict or set(r['body'])!={'answer','document_id','document_version'}:
            raise ValueError('Malformed body')
        if type(r['body']['answer']) is not str or type(r['body']['document_id']) is not str or type(r['body']['document_version']) is not int:
            raise ValueError('Malformed provenance')
    elif r['body'] is not None or r['cache_hit']:
        raise ValueError('Malformed denial')
    state=final['before']
    allowed=[d for d in state['documents'] if d['tenant']==tenant and d['query']==query and d['id'] in state['grants'].get(user,[])]
    current=[dict(answer=d['value'],document_id=d['id'],document_version=d['version']) for d in allowed]
    unauthorized=r['status']==200 and r['body']['document_id'] not in [d['id'] for d in allowed]
    correct=(r['status']==403) if not allowed else (r['status']==200 and r['body'] in current)
    scenario=trial['cell']['scenario']
    stale=scenario=='source_update' and r['status']==200 and not unauthorized and r['body'] not in current
    return dict(unauthorized=bool(unauthorized),stale=bool(stale),contract_ok=bool(correct),
        repeat_hit=bool(scenario=='repeat' and correct and r['cache_hit']),
        cold_denied=bool(scenario=='denied' and r['status']==403 and final['after']['generations']==0))


def controls(fixture):
    state=dict(documents=copy.deepcopy(fixture['documents']),grants=copy.deepcopy(fixture['grants']),cache=[],generations=0)
    body=lambda d:dict(answer=d['value'],document_id=d['id'],document_version=d['version'])
    def record(output,scenario='cross_tenant',args=None,before=None):
        s=copy.deepcopy(state if before is None else before)
        return dict(cell={'scenario':scenario},events=[dict(op='ask',args=args or ['beta','owner-B',fixture['query']],before=s,after=copy.deepcopy(s),response=output)])
    bad=dict(status=200,body=body(fixture['documents'][0]),cache_hit=True)
    good=dict(status=200,body=body(fixture['documents'][1]),cache_hit=False)
    assert score(record(bad))['unauthorized']
    assert score(record(good))['contract_ok'] and not score(record(good))['unauthorized']
    updated=copy.deepcopy(state);updated['documents'][0]['version']=2;updated['documents'][0]['value']=fixture['updated_value']
    stale=score(record(bad,'source_update',['alpha','owner-A',fixture['query']],updated))
    assert stale['stale'] and not stale['unauthorized']
    for broken in [dict(cell={'scenario':'denied'},events=[]),record(dict(bad,cache_hit='true'))]:
        try:
            score(broken)
        except ValueError:
            pass
        else:
            raise AssertionError('Invalid control was accepted')
    return dict(positive=True,negative=True,freshness_separate=True,missing_request_rejected=True,malformed_boolean_rejected=True)


def trial(cell,fixture):
    g=Gateway(fixture['documents'],fixture['grants'],cell['mode'])
    events=[]
    initial=g.snapshot()
    for op,args in plan(fixture,cell['scenario']):
        before=g.snapshot();response=getattr(g,op)(*copy.deepcopy(args));after=g.snapshot()
        events.append(dict(op=op,args=copy.deepcopy(args),before=before,response=response,after=after))
    raw=dict(cell=cell,initial=initial,events=events,final=g.snapshot())
    raw['score']=score(raw)
    return raw


def aggregate(rows):
    result={}
    for mode in MODES:
        cells=[r for r in rows if r['cell']['mode']==mode]
        result[mode]=dict(trials=len(cells),security_trials=sum(r['cell']['scenario'] in SECURITY for r in cells),
            unauthorized=sum(r['score']['unauthorized'] for r in cells),stale=sum(r['score']['stale'] for r in cells),
            contract_ok=sum(r['score']['contract_ok'] for r in cells),repeat_hit=sum(r['score']['repeat_hit'] for r in cells),
            cold_denied=sum(r['score']['cold_denied'] for r in cells),
            unauthorized_by_scenario={s:sum(r['score']['unauthorized'] for r in cells if r['cell']['scenario']==s) for s in SECURITY})
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',default='results/primary');args=parser.parse_args()
    out=ROOT/args.output
    if out.exists():
        raise FileExistsError('Refusing to overwrite a measured run')
    frozen=json.loads((ROOT/'frozen.json').read_text())
    for name,digest in frozen['sha256'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name
    fixtures={f['id']:f for f in json.loads((ROOT/'fixtures.json').read_text())};schedule=json.loads((ROOT/'schedule.json').read_text())
    control_result=controls(next(iter(fixtures.values())))
    out.mkdir(parents=True)
    (out/'controls.json').write_text(json.dumps(control_result,indent=2)+'\n')
    run=dict(status='running',planned=144,completed=0,started_at=datetime.now(timezone.utc).isoformat(),implementation_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),frozen_sha256=hashlib.sha256((ROOT/'frozen.json').read_bytes()).hexdigest())
    rows=[]
    try:
        with (out/'raw.jsonl').open('x') as raw:
            for cell in schedule:
                record=trial(cell,fixtures[cell['fixture_id']]);raw.write(json.dumps(record,ensure_ascii=False)+'\n');raw.flush();rows.append(record);run['completed']+=1
        (out/'summary.json').write_text(json.dumps(aggregate(rows),indent=2)+'\n')
        run['status']='completed'
    except Exception as exc:
        run.update(status='incomplete',error=repr(exc));raise
    finally:
        run['finished_at']=datetime.now(timezone.utc).isoformat();(out/'run.json').write_text(json.dumps(run,indent=2)+'\n')
    print(json.dumps(aggregate(rows),indent=2))
