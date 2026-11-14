"""Non-chest reward sources of the complete randomizer.

Every source becomes an *entry* with the same fields as a chest group of
``remake_world.match_locations`` plus ``source`` and ``form``:

* ``skulltula`` (gold skulltulas): ``Dynamic.Drop__DropActor`` added to the
  enemy, world form. A token placed back on a skulltula leaves it untouched;
* ``shop`` (shelf items): ``Gyaml`` of the shelf actor, shop form;
* ``freestanding`` (heart pieces, rupees and hearts placed in the world):
  ``Gyaml`` of the pickup, world form;
* ``pots``/``bushes``/``rocks``/``crates``/``beehives``/``trees``: explicit native
  ``Drop__DropActor`` of the object, world form (these objects respawn).
  Empty rocks (no drop field at all) receive a new ``Drop__DropActor`` when
  their pack declares it as an instance parameter. Trees (``Obj_Tree_*``) have none either
  and receive one the same way; trees whose drop table is explicitly ``None``
  stay vanilla. Colossus palms are left out (drop never observed);
* ``npc`` (NPC and minigame gifts): the item parameter of the giving event,
  event form. Trade items, songs, cows and masks are never touched;
* ``scrub`` (one-time business scrubs: upgrades and heart pieces): the item
  parameter of their purchase sub-flow, event form; its price follows the option;
* ``boss`` (spiritual stones and medallions), ``fairy`` (great fairy rewards)
  and ``quest`` (story rewards: ocarinas, Zelda's letter, light arrows,
  Biggoron's sword): the item parameter of their giving cutscene, event form;
* ``song`` (the 12 song cutscenes): their silent add, event form; the melody
  teaching and the text-only get are handled by ``song_adapter``;
* ``bossheart`` (boss heart containers): ``Gyaml`` of the placed container,
  world form.

Only static evidence backs these adapters; each family needs an in-game pilot.
"""
from collections import defaultdict

from oot_rando.game.item_forms import WORLD_CANONICAL
from oot_rando.game.randomizer_categories import candidate_category
from oot_rando.game.remake_world import FOLDER_AREAS, FOLDER_DUNGEON, actor_item

GIVE_PARAMS = ('ActorName', 'ReveiveItem', 'ReceiveItem', 'TakenRewardActor', 'Actor')
ENVIRONMENT = ('pots', 'bushes', 'rocks', 'crates', 'beehives', 'trees')
FREESTANDING_JUNK = ('Obj_Rupee_Green', 'Obj_Rupee_Blue', 'Obj_Rupee_Red', 'Obj_Rupee_Purple',
                     'Obj_Rupee_Gold', 'Obj_Heart')
ENV_DROPS = FREESTANDING_JUNK
# Sources without any vanilla drop that still accept an instance Drop__DropActor
# (most rocks of the remake: only 14 of 311 have an explicit drop). Empty pots and
# crates too (Discord 14/11: Kakariko's 30 Obj_Pot_A_08 and every Hyrule Castle pot
# and crate were left out; Obj_Pot_A_01/A_08 and Obj_BrokenBox_A_01 expose
# Drop__DropActor per instance). Pots/crates with a random drop table stay vanilla.
EMPTY_SOURCES = ('rocks', 'pots', 'crates', 'trees')
EMPTY_VANILLA = 'Rupee (1)'
SKIP_FOLDERS = ('DreamWorld', 'SageRoom')

# Shelf actor → AP shop item. Items referenced by the AP logic keep their name;
# the others are remake-only purchases. Bombchu sizes differ from N64.
SHOP_ITEMS = {
    'Shop_Bottle_BlueFire': 'Buy Blue Fire', 'Shop_Bottle_Bug': 'Buy Bottle Bug', 'Shop_Bottle_Fish': 'Buy Fish',
    'Shop_Bottle_Fairy': "Buy Fairy's Spirit", 'Shop_Weapon_Shield_Deku': 'Buy Deku Shield',
    'Shop_Weapon_Shield_Hylian': 'Buy Hylian Shield', 'Shop_Armor_Goron': 'Buy Goron Tunic',
    'Shop_Armor_Zora': 'Buy Zora Tunic', 'Shop_DekuStick': 'Buy Deku Stick (1)',
    'Shop_DekuNutBundle_01': 'Buy Deku Nut (5)', 'Shop_DekuNutBundle_02': 'Buy Deku Nut (10)',
    'Shop_BombchuBundle_01': 'Buy Bombchu (10)', 'Shop_BombchuBundle_02': 'Buy Bombchu (20)',
    'Shop_BombchuBundle_03': 'Buy Bombchu (5)', 'Shop_BombchuBundle_04': 'Buy Bombchu (5)',
    'Shop_BombchuBundle_05': 'Buy Bombchu (5)', 'Shop_BombchuBundle_06': 'Buy Bombchu (10)',
    'Shop_BombchuBundle_07': 'Buy Bombchu (20)', 'Shop_BombchuBundle_08': 'Buy Bombchu (20)',
}
SHOP_EXCLUDED_PREFIXES = ('Shop_Mask_', 'Shop_Board_', 'Shop_Item_Base', 'Shop_Sword_')

# NPC gifts: (AP locations, guard locations, event file stem, ((event, vanilla actor), …)).
# All branches of one gift (e.g. medium/large bag) receive the same item. Guard
# locations only add their access rule (age known in the remake, not in AP).
NPC_GIFTS = (
    (('Market Bombchu Bowling First Prize',), (), 'MiniGame_BombchuBowling',
     (('Event304', 'Item_BombBag_Medium'), ('Event306', 'Item_BombBag_Large'))),
    (('Market Bombchu Bowling Second Prize',), (), 'MiniGame_BombchuBowling', (('Event143', 'Obj_Heart_Piece'),)),
    (('LH Child Fishing',), (), 'MiniGame_Fishing', (('Event573', 'Obj_Heart_Piece'), ('Event821', 'Obj_Heart_Piece'))),
    (('LH Adult Fishing',), (), 'MiniGame_Fishing', (('Event579', 'Item_Scale_Gold'), ('Event822', 'Item_Scale_Gold'))),
    (('ZR Frogs Ocarina Game', 'ZR Frogs in the Rain'), (), 'MiniGame_FrogTenors', (('Event384', 'Obj_Heart_Piece'),)),
    (('Market Shooting Gallery Reward',), (), 'MiniGame_HitTarget',
     (('Event241', 'Item_BulletBag_Medium'), ('Event378', 'Item_BulletBag_Large'))),
    (('Kak Shooting Gallery Reward',), (), 'MiniGame_HitTarget',
     (('Event381', 'Item_Quiver_Medium'), ('Event242', 'Item_Quiver_Large'))),
    (('ZD Diving Minigame',), (), 'MiniGame_Diving', (('Event21', 'Item_Scale_Silver'),)),
    (('GF HBA 1500 Points',), (), 'Minigame_HorsebackArchery',
     (('Event320', 'Item_Quiver_Medium'), ('Event319', 'Item_Quiver_Large'))),
    (('GF HBA 1000 Points',), (), 'Minigame_HorsebackArchery', (('Event322', 'Obj_Heart_Piece'),)),
    (('GC Rolling Goron as Child',), (), 'Npc_Goron_006_Child',
     (('Event58', 'Item_BombBag_Medium'), ('Event92', 'Item_BombBag_Large'))),
    (('Deku Theater Skull Mask',), (), 'LostWood_ScrubForestStageElder_SkullMaskFirst',
     (('Event29', 'Item_StickBag_Medium'), ('Event32', 'Item_StickBag_Large'))),
    (('Deku Theater Mask of Truth',), (), 'LostWood_ScrubForestStageElder_TrueMaskFirst',
     (('Event2', 'Item_NutBag_Medium'), ('Event31', 'Item_NutBag_Large'))),
    (('LW Target in Woods',), (), 'Dm_LostWood_0040',
     (('Event30', 'Item_BulletBag_Medium'), ('Event17', 'Item_BulletBag_Large'))),
    (('LW Skull Kid',), (), 'Npc_SkullKid_Child', (('Event71', 'Obj_Heart_Piece'),)),
    (('LW Ocarina Memory Game',), (), 'Npc_SkullKid_Child_02', (('Event24', 'Obj_Heart_Piece'),)),
    (('Market Lost Dog',), (), 'SubEvent_FindRichard', (('Event16', 'Obj_Heart_Piece'),)),
    # The remake gives this heart piece to the child scientist only.
    (('LH Lab Dive',), ('LH Child Fishing',), 'Npc_Hylia_045_Child', (('Event113', 'Obj_Heart_Piece'),)),
    # Only the adult man on the roof gives the heart piece in the remake.
    (('Kak Man on Roof',), ('Kak Anju as Adult',), 'Npc_Hylia_001_Adult', (('Event4', 'Obj_Heart_Piece'),)),
    (('Graveyard Dampe Gravedigging Tour',), (), 'Npc_Hylia_Dampe_001', (('Event628', 'Obj_Heart_Piece'),)),
    (('GC Darunias Joy',), (), 'Dm_Goron_0030', (('Event127', 'Item_Gauntlet_Goron'),)),
    (('Kak Anju as Child',), (), 'Minigame_CatchCucco', (('Event181', 'Item_Bottle'),)),
    (('Market 10 Big Poes',), (), 'Npc_Hylia_048_BottleShop', (('Event329', 'Item_Bottle'),)),
    (('LLR Talons Chickens',), (), 'Minigame_FindOutCucco', (('Event23', 'Item_Bottle_Milk'),)),
    (('Kak 10 Gold Skulltula Reward',), (), 'GatheringTokenGold', (('Event398', 'Item_Wallet_Medium'),)),
    (('Kak 20 Gold Skulltula Reward',), (), 'GatheringTokenGold', (('Event75', 'Item_AgonyStone'),)),
    (('Kak 30 Gold Skulltula Reward',), (), 'GatheringTokenGold', (('Event194', 'Item_Wallet_Large'),)),
    (('Kak 40 Gold Skulltula Reward',), (), 'GatheringTokenGold', (('Event200', 'Item_BombchuBundle_Large'),)),
    (('Kak 50 Gold Skulltula Reward',), (), 'GatheringTokenGold', (('Event219', 'Obj_Heart_Piece'),)),
)
# Never shuffled, whatever the options (documented exclusions).
EXCLUDED_NPC_LOCATIONS = ('DMT Biggoron', 'Kak Anju as Adult', 'GC Medigoron', 'Wasteland Bombchu Salesman',
                          'ZR Magic Bean Salesman', 'HC Malon Egg', 'HC Zeldas Letter', 'HF Ocarina of Time Item',
                          'LH Underwater Item', 'Hideout Gerudo Membership Card', 'LH Sun')
# Cutscene rewards: (source, AP locations, guards, ((event file stem, event, vanilla actor), ...)).
# Every site of one reward gets the same item: the visible "get" box and, when
# the cutscene adds the item silently first (ocarinas), that pouch addition too.
EVENT_GIFTS = (
    # Dungeon rewards, given after the boss (Deku Tree, Darunia, Ruto, sages, Rauru).
    ('boss', ('Queen Gohma',), (), (('Dm_Kokiri_0130', 'Event22', 'Item_Stone_Forest'),)),
    ('boss', ('King Dodongo',), (), (('Dm_DeathMtTrail_0025', 'Event26', 'Item_Stone_Fire'),)),
    ('boss', ('Barinade',), (), (('Dm_InsideJabu_Jabu_0030', 'Event181', 'Item_Stone_Water'),
                                 ('Dm_ZoraFountain_0030', 'Event3', 'Item_Stone_Water'))),
    ('boss', ('Phantom Ganon',), (), (('Dm_Awake_Forest_Get', 'Event13', 'Item_Medal_Forest'),)),
    ('boss', ('Volvagia',), (), (('Dm_Awake_Fire_Get', 'Event13', 'Item_Medal_Fire'),)),
    ('boss', ('Morpha',), (), (('Dm_Awake_Water_Get', 'Event13', 'Item_Medal_Water'),)),
    ('boss', ('Bongo Bongo',), (), (('Dm_Awake_Shadow_Get', 'Event3', 'Item_Medal_Shadow'),)),
    ('boss', ('Twinrova',), (), (('Dm_Awake_Spirit_Get', 'Event14', 'Item_Medal_Spirit'),)),
    ('boss', ('Links Pocket',), (), (('Dm_SageRoom_0005', 'Event48', 'Item_Medal_Light'),)),
    # Great fairies.
    ('fairy', ('HC Great Fairy Reward',), (), (('Dm_FairyFountain_Din', 'Event212', 'Item_DinFire'),)),
    ('fairy', ('ZF Great Fairy Reward',), (), (('Dm_FairyFountain_Frore', 'Event174', 'Item_FaroreWind'),)),
    ('fairy', ('Colossus Great Fairy Reward',), (), (('Dm_FairyFountain_Nayru', 'Event163', 'Item_NayruLove'),)),
    ('fairy', ('DMT Great Fairy Reward',), (), (('Dm_FairyFountain_Power', 'Event141', 'Item_FairyBless_MP'),)),
    ('fairy', ('DMC Great Fairy Reward',), (), (('Dm_FairyFountain_Wisdom', 'Event144', 'Item_FairyBless_MPDouble'),)),
    ('fairy', ('OGC Great Fairy Reward',), (), (('Dm_FairyFountain_Courage', 'Event144',
                                                 'Item_FairyBless_DefenseDouble'),)),
    # Story rewards.
    ('quest', ('LW Gift from Saria',), (), (('Dm_Kokiri_0155', 'Event68', 'Item_Ocarina_Fairy'),
                                            ('Dm_Kokiri_0155', 'Event77', 'Item_Ocarina_Fairy'))),
    ('quest', ('HF Ocarina of Time Item',), (), (('Dm_MelodyGet_Time', 'Event70', 'Item_Ocarina_Time'),
                                                 ('Dm_MelodyGet_Time', 'Event229', 'Item_Ocarina_Time'))),
    ('quest', ('HC Zeldas Letter',), (), (('Dm_HrlCastle_0050', 'Event59', 'Item_ZeldaLetter'),)),
    ('quest', ('ToT Light Arrows Cutscene',), (), (('Dm_TimeTemple_0130', 'Event85', 'Item_Arrow_Light'),)),
    ('quest', ('DMT Biggoron',), (), (('Npc_Goron_Biggoron_Adult', 'Event123', 'Item_Sword_Biggoron'),)),
)
# Song locations: the silent add of each song cutscene (see patching/song_adapter.py).
from oot_rando.patching.song_adapter import song_gifts as _song_gifts  # noqa: E402
EVENT_GIFTS = EVENT_GIFTS + _song_gifts()
# One-time business scrubs (``Enemy_Scrub_Business_Common``): the item sold is the
# ``ActorName`` of each ``SimpleShopSub_Scrub_Business_OneTime`` call (one per
# branch: e.g. medium or large bag depending on the pouch), the price its
# ``Price``. Each scrub has its own saved flag, set when the purchase succeeds
# (then the scrub leaves). Scrubs selling refills (3 choices, repeatable) and
# those of the dream world (boss rush) are not checks.
# (AP location, flow stem, ((event, vanilla actor, vanilla price), …), native saved flag)
SCRUB_GIFTS = (
    ('LW Deku Scrub Near Bridge', 'Enemy_Scrub_Business_Common',
     (('Event322', 'Item_StickBag_Medium', 40), ('Event317', 'Item_StickBag_Large', 40),
      ('Event555', 'Item_StickBag_Medium', 40)), 'LostWood_Enemy_Scrub_Business_DekuStickPouch_01'),
    ('LW Deku Scrub Grotto Front', 'Enemy_Scrub_Business_Common',
     (('Event326', 'Item_NutBag_Medium', 40), ('Event318', 'Item_NutBag_Large', 40)),
     'Lostwood_Enemy_Scrub_Business_DekuNutsPouch_01'),
    # Hidden scrub of Hyrule Field (``Secret`` talk).
    ('HF Deku Scrub Grotto', 'Enemy_Scrub_Business_Common', (('Event645', 'Obj_Heart_Piece', 100),),
     'HyruleField_Enemy_Scrub_Business_HeartPiece_01'),
    # The remake's crater scrub (child map only) sells a heart piece, not bombs.
    ('DMC Deku Scrub', 'Enemy_Scrub_Business_Common', (('Event293', 'Obj_Heart_Piece', 100),),
     'DeathMountain_Enemy_Scrub_Business_HeartPiece_01'),
)
SCRUB_LOW_PRICE = 10
# Remake starting wallet: 200 rupees (Pouch_Wallet_Small ExpansionMaxNumActor
# MaxNum 200; then 500 and 1000), not the original game's 99 (issue #17).
CHILD_WALLET = 200
# Highest 'random' scrub price: kept at 99 so existing seeds replay identically.
SCRUB_RANDOM_MAX = 99
EVENT_SOURCES = ('npc', 'boss', 'fairy', 'quest', 'scrub', 'song')
# Boss heart container of each dungeon map (one placed Obj_Heart_Container each).
BOSS_HEARTS = {
    'InsideTheDekuTree': 'Deku Tree Queen Gohma Heart', 'DodongoCavern': 'Dodongos Cavern King Dodongo Heart',
    'InsideJabuJabuBelly': 'Jabu Jabus Belly Barinade Heart', 'ForestTemple': 'Forest Temple Phantom Ganon Heart',
    'FireTemple': 'Fire Temple Volvagia Heart', 'WaterTemple': 'Water Temple Morpha Heart',
    'ShadowTemple': 'Shadow Temple Bongo Bongo Heart', 'SpiritTemple': 'Spirit Temple Twinrova Heart',
}


def event_paths(members, stem):
    """Base and ``.110`` update variants of an event flow."""
    return [path for path in (f'Event/EventFlow/{stem}.bfevfl.zs', f'Event/EventFlow/{stem}.110.bfevfl.zs')
            if path in members]


def _entry(source, form, gid, folder, before, vanilla, ident=''):
    return {'id': gid, 'source': source, 'form': form, 'folder': folder, 'hash': ident, 'actor': before,
            'before': before, 'vanilla': vanilla, 'variants': [], 'event': None,
            'dungeon': FOLDER_DUNGEON.get(folder), 'kind': 'junk', 'ap': [], 'guards': [], 'reason': None}


def scan_map_sources(maps, instance_param=None, world_respawn=None):
    """Entries of map-based sources. ``maps`` maps resource → {'root': …}.

    ``instance_param(actor, field)`` tells whether a field is an instance
    parameter of the actor pack; ``world_respawn(actor)`` whether a placed
    pickup respawns. Both default to the conservative answer (refuse).
    """
    instance_param = instance_param or (lambda actor, field: False)
    world_respawn = world_respawn or (lambda actor: True)
    entries = {}

    def add(source, form, gid, folder, before, vanilla, variant, ident):
        variant.setdefault('position', position)
        entry = entries.get(gid)
        if entry is None:
            entry = entries[gid] = _entry(source, form, gid, folder, before, vanilla, ident)
        elif entry['before'] != before:
            entry['reason'] = 'variant_mismatch'
        entry['variants'].append(variant)

    for path in sorted(maps):
        folder = path.split('/')[1]
        if folder in SKIP_FOLDERS:
            continue
        for index, actor in enumerate(maps[path]['root'].get('Actors', [])):
            name = actor.get('Gyaml', '')
            ident = actor.get('Hash')
            if type(ident) is not int:
                continue
            dynamic = actor.get('Dynamic') if isinstance(actor.get('Dynamic'), dict) else {}
            ident = str(ident)
            position = actor.get('Translate')
            if name == 'Enemy_Skulltula_Gold':
                before = dynamic.get('Drop__DropActor')
                add('skulltula', 'world', f'{folder}#gs#{ident}', folder, 'Obj_Token_Gold', 'Gold Skulltula Token',
                    {'resource': path, 'index': index, 'field': 'Drop__DropActor', 'before': before}, ident)
                if before is not None:
                    entries[f'{folder}#gs#{ident}']['reason'] = 'existing_drop'
            elif name == 'Obj_Heart_Container':
                gid = f'{folder}#heart#{ident}'
                add('bossheart', 'world', gid, folder, name, 'Heart Container',
                    {'resource': path, 'index': index, 'field': 'Gyaml', 'before': name}, ident)
                if 'Presence' in actor:
                    entries[gid]['reason'] = 'conditional_presence'
            elif name == 'Obj_Heart_Piece' or (name in FREESTANDING_JUNK and not world_respawn(name)):
                gid = f'{folder}#free#{ident}'
                add('freestanding', 'world', gid, folder, name, actor_item(WORLD_CANONICAL.get(name, name), folder),
                    {'resource': path, 'index': index, 'field': 'Gyaml', 'before': name}, ident)
                if 'Presence' in actor:
                    entries[gid]['reason'] = 'conditional_presence'
            elif name.startswith('Shop_') and not name.startswith(SHOP_EXCLUDED_PREFIXES):
                slot = dynamic.get('ShopItemIndex', 0)
                gid = f'{folder}#shop#{name}#{slot}'
                add('shop', 'shop', gid, folder, name, SHOP_ITEMS.get(name, 'Remake: ' + name),
                    {'resource': path, 'index': index, 'field': 'Gyaml', 'before': name}, ident)
            else:
                category = candidate_category(actor)
                drop = dynamic.get('Drop__DropActor')
                if category in EMPTY_SOURCES and not any(k.startswith('Drop__') for k in dynamic) \
                        and 'Respawn' not in name and instance_param(name, 'Drop__DropActor'):
                    # Empty object whose pack exposes Drop__DropActor per instance:
                    # the field is added (like gold skulltulas), filler by default.
                    gid = f'{folder}#{category}#{ident}'
                    add(category, 'world', gid, folder, None, EMPTY_VANILLA,
                        {'resource': path, 'index': index, 'field': 'Drop__DropActor', 'before': None}, ident)
                    continue
                if category not in ENVIRONMENT or drop not in ENV_DROPS:
                    continue
                gid = f'{folder}#{category}#{ident}'
                add(category, 'world', gid, folder, drop, actor_item(WORLD_CANONICAL[drop], folder),
                    {'resource': path, 'index': index, 'field': 'Drop__DropActor', 'before': drop}, ident)
                if 'Respawn' in name or any(dynamic.get(k) for k in ('Drop__DropTable', 'Drop__DropTableOverWrite')):
                    entries[gid]['reason'] = 'drop_table_or_respawn_variant'
                elif any(k in dynamic for k in ('Drop__CheckActor', 'Drop__DropActor_Substitute', 'GetEventName')):
                    entries[gid]['reason'] = 'special_drop_behavior'
                elif not instance_param(name, 'Drop__DropActor'):
                    entries[gid]['reason'] = 'instance_parameter_not_proven'
    for entry in entries.values():
        if entry['reason'] is None and len({v['resource'] for v in entry['variants']}) != len(entry['variants']) \
                and entry['source'] != 'shop':
            entry['reason'] = 'ambiguous_hash'
    return entries


def scan_npc_sources(members, read_event):
    """Entries of NPC gifts and cutscene rewards. ``read_event(path)`` returns a parsed ``evfl.EventFlow``."""
    gifts = [('npc', ap, guards, tuple((stem, event, actor) for event, actor in sites))
             for ap, guards, stem, sites in NPC_GIFTS] + list(EVENT_GIFTS)
    gifts += [('scrub', (ap,), (), tuple((stem, event, actor) for event, actor, _ in sites))
              for ap, stem, sites, _ in SCRUB_GIFTS]
    entries = scan_event_sources(members, read_event, gifts)
    for ap, stem, sites, flag in SCRUB_GIFTS:
        entry = entries['scrub#' + ap]
        entry['native_flag'] = flag
        prices = {event: price for event, _, price in sites}
        entry['price'] = max(prices.values())
        for variant in list(entry['variants']):
            events = {e.name: e for e in read_event(variant['resource']).flowchart.events}
            event = events[variant['event']]
            if event.data.params.data.get('Price') != prices[variant['event']]:
                entry.update(kind='junk', ap=[], reason='event_param_mismatch')
                continue
            variant['price'] = prices[variant['event']]
    return entries


def scrub_price(option, rng_key, entry):
    """Price of a shuffled scrub for the ``shuffle_scrubs`` option value."""
    if option == 'low':
        return SCRUB_LOW_PRICE
    if option == 'random':
        import hashlib
        digest = hashlib.sha256((rng_key + '\0scrub-price\0' + entry['id']).encode('utf-8')).digest()
        return SCRUB_LOW_PRICE + int.from_bytes(digest[:8], 'big') % (SCRUB_RANDOM_MAX - SCRUB_LOW_PRICE + 1)
    return entry['price']


def scan_event_sources(members, read_event, gifts):
    from evfl.event import ActionEvent, SubFlowEvent
    entries, flows = {}, {}

    def flow_of(path):
        if path not in flows:
            flows[path] = read_event(path)
        return flows[path]

    for source, ap, guards, sites in gifts:
        gid = ('npc#' if source == 'npc' else source + '#') + ap[0]
        first = sites[0][2]
        entry = _entry(source, 'event', gid, 'Npc', first, actor_item(first, ''))
        entry.update(kind='exact' if len(ap) == 1 else 'group', ap=list(ap), guards=list(guards),
                     actors=sorted({actor for _, _, actor in sites}))
        for stem, name, before in sites:
            paths = event_paths(members, stem)
            if not paths:
                entry.update(kind='junk', ap=[], reason='event_missing')
            for path in paths:
                events = {event.name: event for event in flow_of(path).flowchart.events}
                event = events.get(name)
                params = getattr(event.data, 'params', None) if event else None
                keys = [k for k in GIVE_PARAMS if params is not None and params.data.get(k) == before]
                if not isinstance(getattr(event, 'data', None), (ActionEvent, SubFlowEvent)) or len(keys) != 1:
                    # The .110 update may drop an event: only the base file is mandatory.
                    if path.endswith('.110.bfevfl.zs') and event is None:
                        continue
                    entry.update(kind='junk', ap=[], reason='event_param_mismatch')
                    continue
                entry['variants'].append({'resource': path, 'event': name, 'param': keys[0], 'before': before})
        entries[gid] = entry
    return entries


# Kokiri Forest spots, from remake coordinates (x, y, z). Objects of the child
# map in the village are reachable at the start; their AP "anchor" proves it.
# Mido stands at x = 26 on the path to the Deku Tree (x = 103); the storms
# grotto lies underground around (-60, 104, -63); the bean platform rupees
# circle (21.5, 117, -14) and only exist in the adult map.
KF_SPOT_SOURCES = ('pots', 'freestanding', 'rocks', 'bushes', 'crates')
KF_MIDO_GATE_X = 26.0
KF_GROTTO = ((-60.0, 104.0, -63.0), 16.0)
KF_BEAN_PLATFORM = ((21.5, 117.0, -14.0), 4.0)
KF_ANCHOR_CHILD = ('KF Links House Pot',)
KF_ANCHOR_ADULT = ('KF Links House Pot', 'Master Sword Pedestal')
KF_ANCHOR_BEAN = ('KF Bean Platform Red Rupee',)


def _near(position, sphere):
    (cx, cy, cz), radius = sphere
    x, y, z = position
    return (x - cx) ** 2 + (y - cy) ** 2 + (z - cz) ** 2 <= radius ** 2


def kokiri_spot(entry):
    """AP anchors proving access to a Kokiri Forest object, or None (unknown spot)."""
    if entry['folder'] != 'KokiriForest' or entry['source'] not in KF_SPOT_SOURCES:
        return None
    positions = [v.get('position') for v in entry['variants']]
    if not positions or any(not isinstance(p, (list, tuple)) or len(p) != 3 for p in positions):
        return None
    resources = {v['resource'] for v in entry['variants']}
    if not all('_Adult_' in r or '_Child_' in r for r in resources):
        return None
    # One reward for both ages: the child copy is enough to collect it.
    child = any('_Child_' in r for r in resources)
    adult = not child
    if all(_near(p, KF_BEAN_PLATFORM) for p in positions):
        return KF_ANCHOR_BEAN if adult else None
    if any(_near(p, KF_GROTTO) or p[0] >= KF_MIDO_GATE_X for p in positions):
        return None
    return KF_ANCHOR_CHILD if child else KF_ANCHOR_ADULT


def match_sources(entries, data, logic, used=()):
    """Assign AP locations to map-based entries (NPC entries come pre-matched)."""
    used = set(used)
    by_type = defaultdict(list)
    for location in logic.location_names():
        areas = data.location_areas(location) or ()
        if 'Master Quest' in areas and 'Vanilla' not in areas:
            continue
        by_type[data.location_type(location)].append((location, data.vanilla_item(location), areas))
    for entry in entries.values():
        if entry['source'] in EVENT_SOURCES:
            used.update(entry['ap'])

    def candidates(types, folder, item=None):
        areas = set(FOLDER_AREAS.get(folder, ()))
        return sorted(l for t in types for l, v, cats in by_type[t]
                      if l not in used and set(cats) & areas and (item is None or v == item))

    groups = defaultdict(list)
    for entry in entries.values():
        if entry['source'] in EVENT_SOURCES or entry['reason']:
            continue
        if entry['source'] == 'bossheart':
            location = BOSS_HEARTS.get(entry['folder'])
            if location and location not in used:
                entry.update(kind='exact', ap=[location])
                used.add(location)
            else:
                entry['reason'] = 'no_reliable_ap_match'
            continue
        if entry['folder'] not in FOLDER_AREAS:
            entry['reason'] = 'remake_only_area'
            continue
        anchors = kokiri_spot(entry)
        if anchors and all(a in logic.location_region for a in anchors):
            entry.update(kind='area', ap=list(anchors), spot=True)
            continue
        groups[(entry['source'], entry['folder'], entry['vanilla'] if entry['source'] == 'freestanding' else '')
               ].append(entry)
    for (source, folder, item), members in sorted(groups.items()):
        if source == 'skulltula':
            options = candidates(('GS Token',), folder)
        elif source == 'shop':
            options = candidates(('Shop',), folder)
        elif source == 'freestanding' and item == 'Piece of Heart':
            options = candidates(('Collectable', 'Freestanding'), folder, item)
        else:
            options = []
        if options and (len(options) == len(members) or source == 'shop'):
            kind = 'exact' if len(options) == 1 and len(members) == 1 else 'group'
            for entry in members:
                entry.update(kind=kind, ap=list(options))
            used.update(options)
        else:
            for entry in members:
                entry.update(kind='area', ap=[])  # resolved by the planner: every check of the area
    for entry in entries.values():
        if entry['kind'] == 'junk' and not entry['reason']:
            entry['reason'] = 'no_reliable_ap_match'
    return entries


def area_locations(data, logic, folder):
    areas = set(FOLDER_AREAS.get(folder, ()))
    return sorted(l for l in logic.location_names()
                  if areas & set(data.location_areas(l) or ())
                  and not ('Master Quest' in (data.location_areas(l) or ())
                           and 'Vanilla' not in (data.location_areas(l) or ()))
                  and data.location_type(l) not in ('HintStone', 'Hint', 'Drop', 'Event'))


def collect(nup, dictionaries, members, maps):
    """All candidate entries of the local game (read-only)."""
    from oot_rando.formats.inspect_resources import Byml, decompress, sarc
    from oot_rando.formats import byml_codec
    from oot_rando.game.item_forms import resolve_components
    from evfl import EventFlow
    packs = {}

    def pack(actor):
        if actor not in packs:
            path = 'Pack/Actor/' + actor + '.pack.zs'
            packs[actor] = sarc(decompress(nup.read(members[path]), dictionaries)) if path in members else None
        return packs[actor]

    def instance_param(actor, field):
        data = pack(actor) or {}
        for path, raw in data.items():
            if 'BlackboardParamTable/' in path and path.endswith('.bgyml'):
                root = Byml(raw).root
                for entry in (root.get('BlackboardParamStringArray', []) if isinstance(root, dict) else []):
                    if entry.get('BBKey') == field and entry.get('IsInstanceParam') is True:
                        return True
        return False

    def world_respawn(actor):
        data = pack(actor)
        if data is None:
            return True
        setting = resolve_components(data, actor, byml_codec).get('ActorGameDataSetting', '')
        return 'NoRespawn' not in setting

    def read_event(path):
        flow = EventFlow()
        flow.read(decompress(nup.read(members[path]), dictionaries))
        return flow

    entries = scan_map_sources(maps, instance_param, world_respawn)
    entries.update(scan_npc_sources(members, read_event))
    return entries


def scan_world(nup, dictionaries, members, progress=None):
    """Maps, chest groups, enemies and the other reward sources."""
    from oot_rando.game.remake_world import scan_maps
    maps, groups, enemies = scan_maps(nup, dictionaries, members, progress)
    return maps, groups, enemies, collect(nup, dictionaries, members, maps)
