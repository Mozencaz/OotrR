"""Small checked graph operations shared by the scene-specific skip adapters.

All edits use our EVFL reader/writer. Original events stay in the resource, so
other adapters' stable event names and the asset verifier remain usable.
"""
import copy

from evfl.event import ActionEvent, SubFlowEvent, SubFlowSwitchEvent
from evfl.util import make_index

from oot_rando.patching.event_patch import _flow
from oot_rando.patching.progressive import FlowEditor, link
from oot_rando.patching.song_lessons import _action, _params, _reach, _redirect

FLOW_DIR = 'Event/EventFlow/'


def path(name):
    return FLOW_DIR + name + '.bfevfl.zs'


class SceneEditor(FlowEditor):
    def __init__(self, raw, name, actor_sources=()):
        super().__init__(raw, name)
        self.events = {e.name: e for e in self.chart.events}
        self.entries = {e.name: e for e in self.chart.entry_points}
        self.actor_sources = actor_sources
        self.serial = max([int(e.name.rsplit('_', 1)[-1]) for e in self.chart.events
                           if e.name.startswith('RandoCinema_') and e.name.rsplit('_', 1)[-1].isdigit()] or [0])

    def actor(self, identifier):
        if not any(str(a.identifier) == identifier for a in self.chart.actors):
            for raw in self.actor_sources:
                if raw is None:
                    continue
                source = next((a for a in _flow(raw).flowchart.actors if str(a.identifier) == identifier), None)
                if source is not None:
                    self.chart.actors.append(copy.deepcopy(source))
                    break
        return super().actor(identifier)

    def unique(self, label):
        self.serial += 1
        name = f'RandoCinema_{label}_{self.serial}'
        if name in self.expected:
            raise ValueError('Scene shortcut already applied: ' + self.name)
        return name

    def act(self, label, actor, action, params=None):
        return self.action(self.unique(label), actor, action, params)

    def call(self, label, flow, entry, params=None):
        return self.subflow(self.unique(label), flow, entry, params)

    def flag(self, flag, value=True):
        return self.act('Flag', 'GameDataActor', 'EventTriggerSetGameDataBool',
                        {'GameDataName': flag, 'Value': value, 'Index': -1})

    def chain(self, events, following=None):
        for event, nxt in zip(events, events[1:] + [following]):
            link(event, nxt)
        return events[0] if events else following

    def clone_action(self, source):
        if not isinstance(source.data, ActionEvent):
            raise ValueError('Expected a native action: ' + source.name)
        return self.act(source.name, *_action(source), _params(source) or None)

    def replace(self, event, first):
        from oot_rando.patching.qol_patches import _predecessors
        if not _predecessors(self.chart, event):
            # An earlier generic timeline/window adapter already retired it.
            return False
        _redirect(self.chart, event, first)
        return True

    def fade(self):
        return self.act('FadeIn', 'UISystemActor', 'EventEventFadeIn',
                        {'Color': 0, 'Length': 1, 'IsNoPlayAnime': False, 'IsWaitEnd': True})

    def wait_loading(self):
        return self.act('Loading', 'UISystemActor', 'EventWaitCloseLoadingFade', {'IsWaitEnd': True})

    def finish(self, report):
        # A skipped ceremony must not pull an already opened quest backwards.
        # Guard every newly replayed request, preserving its continuation.
        from oot_rando.patching.quest_guard import _relink
        for event in list(self.chart.events):
            if not event.name.startswith('RandoCinema_') or _action(event) != (
                    'ChallengeSystemActor', 'EventExecuteProgressChallengeStep'):
                continue
            if any(e.name.startswith('RandoCinema_StepGuard') and event in
                   [v.v for v in (getattr(e.data, 'cases', None) or {}).values()] for e in self.chart.events):
                continue
            params = _params(event)
            quest, step = params['ChallengeName'], params['StepName']
            # A Complete request cannot regress a quest; some quests (notably
            # SageOfLight) do not expose an IsCompleted expression at all.
            if step == 'Complete':
                continue
            resume = event.data.nxt.v
            expression = quest + ('_IsCompleted_Exp' if step == 'Complete' else '_IsAfter_' + step + '_Exp')
            guard = self.switch(self.unique('StepGuard'), 'GameDataActor', 'EventQueryIsGameDataBoolExp',
                                {'GameDataName': expression}, resume, event)
            _relink(self.chart, event, guard)
            if step != 'Complete':
                complete = self.switch(self.unique('CompletedGuard'), 'GameDataActor', 'EventQueryIsGameDataBoolExp',
                                       {'GameDataName': quest + '_IsCompleted_Exp'}, resume, guard)
                _relink(self.chart, guard, complete)
        # Rebuild each entry's direct preload indices. A local callee has its own
        # list; external resources are completed transitively by event_info.
        # An old index pointing at a replaced non-call makes the engine reject an event.
        for entry in self.chart.entry_points:
            reached = {e.name for e in _reach(self.chart, [entry.main_event.v], descend=False)}
            entry._sub_flow_event_indices = [i for i, e in enumerate(self.chart.events)
                                             if isinstance(e.data, (SubFlowEvent, SubFlowSwitchEvent)) and e.name in reached]
        raw, checked = self.write('Cinematic shortcut ' + self.name)
        if checked.flowchart.name != self.chart.name:
            raise ValueError('Cinematic flow identity changed')
        return raw, report


def reward(raw, event_name):
    """The current placement and saved check marker of a native reward event."""
    chart = _flow(raw).flowchart
    events = {e.name: e for e in chart.events}
    event = events[event_name]
    actor = _params(event).get('ActorName', _params(event).get('Actor'))
    if not isinstance(actor, str) or not actor:
        raise ValueError('Reward without a concrete actor: ' + event_name)
    marker = events.get('RandoCollected_' + event_name)
    return {'actor': actor, 'flag': _params(marker).get('GameDataName') if marker else None}


def held_actor(actor):
    """Animated pickup form for equipment/song actors without item-get animation."""
    from oot_rando.game.item_forms import OCARINAS, form_actor
    from oot_rando.patching.progressive import token_family
    if actor in OCARINAS or actor.startswith('Item_Melody_') or token_family(actor) == 'Ocarina':
        return form_actor(actor, 'world')
    return actor


def give(editor, item, following=None):
    """Standard get (including our key/progressive hooks), then the collection marker.

    Ocarinas are displayed through our derived world actor, then added through
    the native equipment actor so they work immediately without a save reload.
    """
    from oot_rando.game.item_forms import OCARINAS
    from oot_rando.patching.progressive import token_family
    actor = item['actor']
    shown = held_actor(actor)
    steps = [editor.act('JoinPlayer', 'Player_Event', 'EventTriggerParticipateEvent'),
             editor.act('UnequipPlayer', 'Player_Event', 'EventPlayerUnequip', {'IsWaitEnd': True}),
             editor.call('Get', 'Dm_SY_GetInEvent', 'GetInEvent_NotTurn_NotNpc',
                         {'ActorName': shown, 'IsNpcEventStarter': False})]
    if actor in OCARINAS:
        steps.append(editor.act('OcarinaGrant', 'PouchSystemActor', 'EventTriggerAddOrRemovePouchContent',
                                 {'Actor': actor, 'Num': 1, 'IsEquipDIrect': False,
                                  'IsSetMessageTargetActorName': False, 'IsGetEvent': False}))
    tail = following
    if item.get('flag'):
        tail = editor.chain([editor.flag(item['flag'])], tail)
    if actor in OCARINAS or token_family(actor) == 'Ocarina':
        # Converter hooks have now run. Equip the highest owned tier, so an
        # unshuffled Fairy Ocarina never downgrades an already owned Time one.
        choices = []
        for tier in OCARINAS:
            equip = editor.act('OcarinaEquip', 'GameDataActor', 'EventTriggerSetGameDataString64',
                               {'GameDataName': 'PlayerStatus.EquipOcarina', 'Value': tier, 'Index': -1})
            link(equip, tail)
            choices.append((tier, equip))
        first = tail
        for tier, equip in choices:
            first = editor.switch(editor.unique('OcarinaOwned'), 'GameDataActor', 'EventQueryIsGameDataBool',
                                  {'GameDataName': 'IsGet.' + tier, 'Index': -1}, equip, first)
        tail = first
    return editor.chain(steps, tail)
