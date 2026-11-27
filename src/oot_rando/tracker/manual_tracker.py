"""Checks ticked by hand in the tracker, one profile per seed and save slot."""
import hashlib
import json
from pathlib import Path


class ManualTracker:
    def __init__(self, directory, seed_id, slot, check_ids):
        if not isinstance(slot, str) or not slot.strip():
            raise ValueError('Give the game profile a name.')
        self.seed_id, self.slot = seed_id, slot
        self.allowed = set(check_ids)
        digest = hashlib.sha256((seed_id + '\0' + slot).encode()).hexdigest()
        self.path = Path(directory) / (digest + '.json')
        self.completed = set()
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if data.get('seed_id') != seed_id or data.get('slot') != slot:
                raise ValueError('Inconsistent tracking profile.')
            self.completed = set(data['completed']) & self.allowed

    def set_completed(self, ident, value):
        if ident not in self.allowed:
            raise ValueError('Check inconnu.')
        updated = set(self.completed)
        updated.add(ident) if value else updated.discard(ident)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps({'schema_version': 1, 'seed_id': self.seed_id,
                                        'slot': self.slot, 'source': 'manual',
                                        'completed': sorted(updated)}, indent=2), encoding='utf-8')
        temporary.replace(self.path)
        self.completed = updated
