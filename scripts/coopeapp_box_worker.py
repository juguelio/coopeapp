#!/usr/bin/env python3
"""Safe polling worker: Box insurance PDFs -> CoopeApp review proposals.

This worker intentionally creates only pending review proposals. It never
approves, deletes, shares, moves Box files, or changes production policies.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import subprocess
import tempfile
import unicodedata
from datetime import date
from pathlib import Path

BOX = Path.home() / '.hermes' / 'tools' / 'box-cli' / 'node_modules' / '.bin' / 'box'
FOLDER_ID = '413696190636'  # CoopeApp pilot / 02 Seguros y Pólizas
STATE_PATH = Path.home() / '.hermes' / 'state' / 'coopeapp-box-worker.json'
VPS = 'coopeapp-vps'

DATE_RE = re.compile(r"(?P<key>Vigencia desde|Vigencia hasta)\s*:\s*(?P<value>\d{4}-\d{2}-\d{2})")
FIELD_RE = re.compile(
    r"^(?P<key>N[uú]mero de p[oó]liza|Aseguradora|Tipo|Obra|Per[ií]odo|Importe|Socios cubiertos)\s*:\s*(?P<value>.*)$",
    re.MULTILINE,
)


def run(cmd: list[str], *, input_text: str | None = None) -> str:
    result = subprocess.run(cmd, input=input_text, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout


def box(*args: str) -> object:
    return json.loads(run([str(BOX), *args, '--json']))


def normalize(value: str) -> str:
    plain = unicodedata.normalize('NFKD', value)
    return ''.join(ch for ch in plain if not unicodedata.combining(ch)).lower()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def parse_pdf(path: Path, file_id: str, version_id: str) -> dict:
    from pypdf import PdfReader
    text = '\n'.join(page.extract_text() or '' for page in PdfReader(str(path)).pages)
    fields = {normalize(m.group('key')): m.group('value').strip() for m in FIELD_RE.finditer(text)}
    dates = {normalize(m.group('key')): m.group('value') for m in DATE_RE.finditer(text)}
    required = ['numero de poliza', 'aseguradora', 'tipo', 'obra', 'periodo', 'importe', 'socios cubiertos']
    missing = [key for key in required if not fields.get(key)]
    if missing or 'vigencia desde' not in dates or 'vigencia hasta' not in dates:
        raise ValueError('missing required fields: ' + ', '.join(missing or ['vigencia']))
    socios = [item.strip() for item in fields['socios cubiertos'].split(',') if item.strip()]
    reasons = []
    if dates['vigencia hasta'] < dates['vigencia desde']:
        reasons.append('fecha_fin anterior a fecha_inicio')
    if dates['vigencia hasta'] < date.today().isoformat():
        reasons.append('póliza vencida')
    if not socios:
        reasons.append('nómina vacía')
    importe = float(fields['importe'].replace('.', '').replace(',', '.'))
    if importe <= 0:
        reasons.append('importe no positivo')
    return {
        'source': {
            'file_id': str(file_id),
            'file_name': path.name,
            'version_id': str(version_id),
            'sha256': sha256(path),
        },
        'proposal': {
            'numero': fields['numero de poliza'],
            'aseguradora': fields['aseguradora'],
            'obra': fields['obra'],
            'fecha_inicio': dates['vigencia desde'],
            'fecha_fin': dates['vigencia hasta'],
            'periodo': fields['periodo'],
            'importe': importe,
            'socios': socios,
            'status': 'needs_correction' if reasons else 'pending_review',
            'reasons': reasons,
        },
        'conflicts': [{'field': 'validation', 'action': 'hold_for_human_review'}] if reasons else [],
    }


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {'seen': {}}
    return json.loads(STATE_PATH.read_text(encoding='utf-8'))


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def write_proposal(payload: dict) -> dict:
    encoded = base64.b64encode(json.dumps(payload, ensure_ascii=False).encode()).decode()
    script = f'''import base64, json
payload = json.loads(base64.b64decode("{encoded}"))
Proposal = env["coop.document.proposal"].sudo()
source = payload["source"]
existing = Proposal.search([("box_file_id", "=", source["file_id"]), ("box_version_id", "=", source["version_id"])], limit=1)
proposal = Proposal.create_from_ingestion(payload)
env.cr.commit()
print(json.dumps({{"proposal_id": proposal.id, "created": not bool(existing), "state": proposal.state, "file_id": proposal.box_file_id, "version_id": proposal.box_version_id}}, ensure_ascii=False))
'''
    output = run([
        'ssh', VPS,
        'cd ~/odoo-coop && docker compose run --rm -T odoo odoo shell -d coop_piloto --stop-after-init',
    ], input_text=script)
    lines = [line.strip() for line in output.splitlines() if line.strip().startswith('{')]
    if not lines:
        raise RuntimeError('Odoo worker returned no JSON: ' + output[-1000:])
    return json.loads(lines[-1])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--force', action='store_true', help='reprocess files despite local state')
    args = parser.parse_args()
    if not BOX.exists():
        raise SystemExit('Box CLI not found: ' + str(BOX))
    raw = box('folders:items', FOLDER_ID, '--fields', 'id,name,type')
    entries = raw if isinstance(raw, list) else raw.get('entries', [])
    state = load_state()
    events = []
    for item in entries:
        if item.get('type') != 'file' or not item.get('name', '').lower().endswith('.pdf'):
            continue
        metadata = box('files:get', str(item['id']), '--fields', 'id,name,file_version')
        version = (metadata.get('file_version') or {}).get('id') or metadata.get('etag')
        key = f"{metadata['id']}:{version}"
        if key in state['seen'] and not args.force:
            continue
        with tempfile.TemporaryDirectory(prefix='coopeapp-box-worker-') as tmp:
            target = Path(tmp) / metadata['name']
            run([str(BOX), 'files:download', str(metadata['id']), '--destination', tmp,
                 '--save-as', metadata['name'], '--overwrite', '--quiet'])
            payload = parse_pdf(target, metadata['id'], version)
        if args.dry_run:
            events.append({'file': metadata['name'], 'dry_run': True, 'payload': payload})
            continue
        result = write_proposal(payload)
        state['seen'][key] = {'file_name': metadata['name'], 'proposal_id': result['proposal_id']}
        save_state(state)
        events.append({'file': metadata['name'], **result})
    if events:
        print(json.dumps({'ok': True, 'events': events}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
