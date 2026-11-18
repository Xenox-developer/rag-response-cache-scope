"""Audit raw transitions and policy outcomes without importing cache or harness."""
import copy
import hashlib
import itertools
import json
from pathlib import Path
import random

ROOT=Path(__file__).resolve().parent
MODES=['query','tenant','context']
SCENARIOS=['repeat','denied','cross_tenant','same_tenant_scope','revoked','source_update']
SECURITY=['cross_tenant','same_tenant_scope','revoked']


def audit():
    frozen=json.loads((ROOT/'frozen.json').read_text())
    for name,digest in frozen['sha256'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name
    fixtures=json.loads((ROOT/'fixtures.json').read_text());by_id={f['id']:f for f in fixtures}
    assert len(fixtures)==8 and len(by_id)==8
    schedule=[dict(id=f['id']+'-'+m+'-'+s,fixture_id=f['id'],mode=m,scenario=s) for f,m,s in itertools.product(fixtures,MODES,SCENARIOS)]
    random.Random(20261118).shuffle(schedule)
    assert schedule==json.loads((ROOT/'schedule.json').read_text())
    out=ROOT/'results/primary';run=json.loads((out/'run.json').read_text())
    assert run['status']=='completed' and run['planned']==run['completed']==144
    assert run['frozen_sha256']==hashlib.sha256((ROOT/'frozen.json').read_bytes()).hexdigest()
    assert json.loads((out/'controls.json').read_text())==dict(positive=True,negative=True,freshness_separate=True,missing_request_rejected=True,malformed_boolean_rejected=True)
    raw=[json.loads(line) for line in (out/'raw.jsonl').read_text().splitlines()]
    assert len(raw)==144 and len({r['cell']['id'] for r in raw})==144
    summary={m:dict(trials=0,security_trials=0,unauthorized=0,stale=0,contract_ok=0,repeat_hit=0,cold_denied=0,unauthorized_by_scenario={s:0 for s in SECURITY}) for m in MODES}
    for cell,row in zip(schedule,raw):
        assert row['cell']==cell
        fixture=by_id[cell['fixture_id']];mode=cell['mode'];scenario=cell['scenario']
        documents=copy.deepcopy(fixture['documents']);grants=copy.deepcopy(fixture['grants']);cache={};generated=0
        def snapshot():
            return dict(documents=sorted(copy.deepcopy(documents),key=lambda d:d['id']),grants={u:sorted(set(ids)) for u,ids in grants.items()},cache=sorted(copy.deepcopy(list(cache.values())),key=lambda b:(b['document_id'],b['document_version'],b['answer'])),generations=generated)
        assert row['initial']==snapshot()
        warm=['alpha','owner-A',fixture['query']]
        if scenario=='denied':
            steps=[('ask',['alpha','reader-A',fixture['query']])]
        else:
            steps=[('ask',warm)]
            if scenario=='revoked':
                steps.append(('set_grants',['owner-A',[]]))
            if scenario=='source_update':
                steps.append(('set_document',[fixture['documents'][0]['id'],fixture['updated_value'],2]))
            second=['beta','owner-B',fixture['query']] if scenario=='cross_tenant' else ['alpha','reader-A',fixture['query']] if scenario=='same_tenant_scope' else warm
            steps.append(('ask',second))
        assert len(row['events'])==len(steps)
        last=None
        for event,(op,args) in zip(row['events'],steps):
            assert event['op']==op and event['args']==args
            assert event['before']==snapshot()
            if op=='set_grants':
                grants[args[0]]=list(args[1]);expected=None
            elif op=='set_document':
                doc=next(d for d in documents if d['id']==args[0]);doc['value']=args[1];doc['version']=args[2];expected=None
            else:
                tenant,user,question=args
                eligible=[d for d in documents if d['tenant']==tenant and d['query']==question and d['id'] in grants.get(user,[])]
                assert len(eligible)<=1
                if mode=='query':
                    key=(question,)
                elif mode=='tenant':
                    key=(tenant,question)
                else:
                    key=None if not eligible else (tenant,question,eligible[0]['id'],eligible[0]['version'],eligible[0]['value'])
                if key in cache:
                    expected=dict(status=200,body=copy.deepcopy(cache[key]),cache_hit=True)
                elif not eligible:
                    expected=dict(status=403,body=None,cache_hit=False)
                else:
                    doc=eligible[0];body=dict(answer=doc['value'],document_id=doc['id'],document_version=doc['version'])
                    cache[key]=copy.deepcopy(body);generated+=1
                    expected=dict(status=200,body=body,cache_hit=False)
                assert type(event['response']['cache_hit']) is bool
                assert type(event['response']['status']) is int
                last=(event,copy.deepcopy(eligible))
            assert event['response']==expected
            assert event['after']==snapshot()
        assert row['final']==snapshot()
        final,eligible=last;r=final['response']
        if r['status']==200:
            assert type(r['body']['document_version']) is int
            assert type(r['body']['document_id']) is type(r['body']['answer']) is str
        unauthorized=r['status']==200 and r['body']['document_id'] not in [d['id'] for d in eligible]
        expected_bodies=[dict(answer=d['value'],document_id=d['id'],document_version=d['version']) for d in eligible]
        correct=(r['status']==403) if not eligible else r['status']==200 and r['body'] in expected_bodies
        stale=scenario=='source_update' and r['status']==200 and not unauthorized and r['body'] not in expected_bodies
        outcomes=dict(unauthorized=bool(unauthorized),stale=bool(stale),contract_ok=bool(correct),repeat_hit=bool(scenario=='repeat' and correct and r['cache_hit']),cold_denied=bool(scenario=='denied' and r['status']==403 and row['final']['generations']==0))
        assert row['score']==outcomes
        s=summary[mode];s['trials']+=1;s['security_trials']+=scenario in SECURITY
        for key,value in outcomes.items():
            s[key]+=value
        if scenario in SECURITY:
            s['unauthorized_by_scenario'][scenario]+=unauthorized
    assert summary==json.loads((out/'summary.json').read_text())
    return dict(passed=True,trials=144,frozen_files=len(frozen['sha256']),summary=summary,notes='Selected deterministic cache counterexamples; no inference, HTTP, embeddings or deployed incidents. Counts are not failure-probability estimates.')


if __name__=='__main__':
    result=audit();(ROOT/'results/audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
