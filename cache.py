from copy import deepcopy


class Gateway:
    def __init__(self, documents, grants, mode):
        if mode not in ('query', 'tenant', 'context'):
            raise ValueError('unknown cache mode')
        self._documents = deepcopy(documents)
        self._grants = {principal: set(ids) for principal, ids in deepcopy(grants).items()}
        self._mode = mode
        self._cache = {}
        self._generations = 0

    def ask(self, tenant, principal, query):
        if self._mode == 'query':
            key = query
        elif self._mode == 'tenant':
            key = (tenant, query)
        else:
            key = None

        if self._mode != 'context' and key in self._cache:
            return {'status': 200, 'body': deepcopy(self._cache[key]), 'cache_hit': True}

        allowed = self._grants.get(principal, set())
        document = next((doc for doc in self._documents
                         if doc['tenant'] == tenant and doc['query'] == query
                         and doc['id'] in allowed), None)
        if document is None:
            return {'status': 403, 'body': None, 'cache_hit': False}

        if self._mode == 'context':
            key = (tenant, query, document['id'], document['version'], document['value'])
            if key in self._cache:
                return {'status': 200, 'body': deepcopy(self._cache[key]), 'cache_hit': True}

        body = {'answer': document['value'], 'document_id': document['id'],
                'document_version': document['version']}
        self._cache[key] = deepcopy(body)
        self._generations += 1
        return {'status': 200, 'body': deepcopy(body), 'cache_hit': False}

    def set_grants(self, principal, ids):
        self._grants[principal] = set(deepcopy(ids))

    def set_document(self, id, value, version):
        for document in self._documents:
            if document['id'] == id:
                document['value'] = value
                document['version'] = version
                return
        raise KeyError(id)

    def snapshot(self):
        return deepcopy({
            'documents': sorted(self._documents, key=lambda doc: doc['id']),
            'grants': {principal: sorted(ids) for principal, ids in self._grants.items()},
            'cache': sorted(self._cache.values(),
                            key=lambda body: (body['document_id'],
                                              body['document_version'], body['answer'])),
            'generations': self._generations,
        })
