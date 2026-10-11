"""Existing IP Fabric with external-evidence filtering and bounded graph expansion."""
import json
from ip_fabric.core import Core, encode
from ip_fabric.index import Index
from hybrid_ai.provider import LMStudioEmbedding
from .compile import load
from .import_go import HERE, digest


def validate(unit):
    if unit['license'] != 'CC-BY-4.0' or unit['review_status'] not in {'external_evidence', 'source_supported_not_expert_reviewed'}:
        raise ValueError('Unreviewed candidate or incompatible license')
    for ref in unit['source_references']:
        path = (HERE / ref['file']).resolve()
        if not path.is_relative_to(HERE.resolve()) or digest(path.read_bytes()) != ref['sha256']:
            raise ValueError('Source integrity mismatch')
        if ref.get('anchor') and ref['anchor'] not in path.read_text(encoding='utf8'):
            raise ValueError('Source anchor missing')


def render(unit):
    return '\n'.join([unit['concept_id'] + ': ' + unit['label'], unit['claim'],
        'Conditions: ' + '; '.join(unit['conditions']),
        'Constraints: ' + '; '.join(unit['constraints']),
        'Prerequisites: ' + ', '.join(unit['prerequisites']),
        'Review: ' + unit['review_status'], 'Curriculum alignment: pending'])


class Retriever:
    def __init__(self, embedder=None):
        self.core = Core(HERE / 'canonical')
        self.embedder = embedder or LMStudioEmbedding()
        if 'nomic' not in self.embedder.signature.lower():
            raise ValueError('Approved Nomic backend required')
        self.index = Index(self.core, HERE / 'index', self.embedder)

    def ingest(self):
        units = load('knowledge_ir.json')
        for u in units:
            validate(u)
        results = []
        for u in units:
            attachments = {'ir.json': encode(u)}
            for ref in u['source_references']:
                p = HERE / ref['file']; attachments[p.name] = p.read_bytes()
            results.append(self.core.ingest(render(u), title=u['label'], source='knowledge_ir_v1',
                source_external_id=u['concept_id'], artifact_type='knowledge_unit',
                project='knowledge-ir-v1', domain='cell_division', status='external_evidence',
                attachments=attachments, evidence=u, author=u['attribution']))
        return {'imports': results, 'index': self.index.update()}

    def retrieve(self, query, concept_id=None):
        records = {}
        for id in self.core.ids():
            meta, text, folder = self.core.read(id)
            if meta['status'] != 'external_evidence':
                continue
            unit = json.loads((folder / 'evidence.json').read_text(encoding='utf8'))
            validate(unit)
            records[unit['concept_id']] = (id, unit)
        if concept_id and concept_id not in records:
            return {'status': 'NOT_VERIFIED', 'reason': 'Unknown concept ID', 'units': [], 'vector_hits': []}
        # Semantic search still executed for evidence discovery, with exact-ID lookup first when supplied.
        exact = [concept_id] if concept_id else []
        hits = self.index.search(query, limit=3, project='knowledge-ir-v1', domain='cell_division', status='external_evidence')
        selected = exact + [h['metadata']['source_external_id'] for h in hits]
        expanded = []
        for cid in selected:
            if cid not in expanded:
                expanded.append(cid)
        for cid in list(expanded):
            u = records[cid][1]
            for parent in u['prerequisites'] + [r['target'] for r in u['relationships']]:
                if parent in records and parent not in expanded:
                    expanded.append(parent)
        return {'status': 'EVIDENCE_FOUND', 'vector_hits': hits, 'units': [records[x][1] for x in expanded],
                'missing_relationship_targets': sorted({r['target'] for x in expanded for r in records[x][1]['relationships'] if r['target'] not in records}),
                'exact_concept': concept_id, 'curriculum_alignment': 'pending'}


if __name__ == '__main__':
    print(json.dumps(Retriever().ingest()))
