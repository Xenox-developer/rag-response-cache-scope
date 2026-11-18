import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from cache import Gateway

F=json.loads((ROOT/'fixtures.json').read_text())[0]


def gateway(mode):
    return Gateway(F['documents'],F['grants'],mode)


class Checks(unittest.TestCase):
    def test_repeat(self):
        for mode in ['query','tenant','context']:
            g=gateway(mode);a=g.ask('alpha','owner-A',F['query']);b=g.ask('alpha','owner-A',F['query'])
            self.assertEqual(a['status'],200);self.assertIs(a['cache_hit'],False)
            self.assertEqual(b['body'],a['body']);self.assertIs(b['cache_hit'],True)
            self.assertEqual(g.snapshot()['generations'],1)

    def test_cross_tenant(self):
        for mode in ['query','tenant','context']:
            g=gateway(mode);g.ask('alpha','owner-A',F['query']);b=g.ask('beta','owner-B',F['query'])
            self.assertEqual(b['body']['document_id'],F['documents'][0 if mode=='query' else 1]['id'])
            self.assertIs(b['cache_hit'],mode=='query')

    def test_role_and_revocation(self):
        for mode in ['query','tenant','context']:
            for revoke in [False,True]:
                g=gateway(mode);g.ask('alpha','owner-A',F['query'])
                if revoke:
                    g.set_grants('owner-A',[])
                r=g.ask('alpha','owner-A' if revoke else 'reader-A',F['query'])
                self.assertEqual(r['status'],403 if mode=='context' else 200)
                self.assertIs(r['cache_hit'],mode!='context')

    def test_updated_version(self):
        for mode in ['query','tenant','context']:
            g=gateway(mode);g.ask('alpha','owner-A',F['query'])
            g.set_document(F['documents'][0]['id'],'NEW',2)
            r=g.ask('alpha','owner-A',F['query'])
            self.assertEqual(r['body']['answer'],'NEW' if mode=='context' else F['documents'][0]['value'])
            self.assertEqual(g.snapshot()['generations'],2 if mode=='context' else 1)

    def test_cold_denied_and_no_negative_cache(self):
        for mode in ['query','tenant','context']:
            g=gateway(mode)
            self.assertEqual(g.ask('alpha','reader-A',F['query']),{'status':403,'body':None,'cache_hit':False})
            self.assertEqual(g.snapshot()['generations'],0);self.assertEqual(g.snapshot()['cache'],[])
            g.set_grants('reader-A',[F['documents'][0]['id']])
            self.assertEqual(g.ask('alpha','reader-A',F['query'])['status'],200)

    def test_same_context_reuse(self):
        g=gateway('context');g.ask('alpha','owner-A',F['query'])
        r=g.ask('alpha','peer-A',F['query'])
        self.assertIs(r['cache_hit'],True);self.assertEqual(g.snapshot()['generations'],1)

    def test_content_change_without_version_bump(self):
        g=gateway('context');g.ask('alpha','owner-A',F['query'])
        g.set_document(F['documents'][0]['id'],'NEW SAME VERSION',1)
        r=g.ask('alpha','owner-A',F['query'])
        self.assertEqual(r['body']['answer'],'NEW SAME VERSION');self.assertIs(r['cache_hit'],False)

    def test_copies_snapshot_and_mode(self):
        import copy
        docs=copy.deepcopy(F['documents']);grants=copy.deepcopy(F['grants'])
        g=Gateway(docs,grants,'context');docs[0]['value']='EXTERNAL';grants['owner-A'].clear()
        r=g.ask('alpha','owner-A',F['query']);r['body']['answer']='CALLER'
        self.assertEqual(g.ask('alpha','owner-A',F['query'])['body']['answer'],F['documents'][0]['value'])
        s=g.snapshot();s['cache'].clear();s['documents'][0]['value']='SNAPSHOT'
        self.assertTrue(g.ask('alpha','owner-A',F['query'])['cache_hit'])
        with self.assertRaises(ValueError):
            gateway('unknown')


if __name__=='__main__':
    r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Checks))
    Path('check-report.json').write_text(json.dumps(dict(tests=r.testsRun,failures=len(r.failures),errors=len(r.errors),passed=r.wasSuccessful())))
    raise SystemExit(not r.wasSuccessful())
