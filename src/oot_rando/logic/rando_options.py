"""Archipelago-style options of the complete randomizer.

Each option keeps its AP OoT name and values so that an AP YAML can be imported.
A value is *supported* only when the generator changes the game **and** the
solver consistently. Unsupported values stay visible in the interface, greyed,
with their reason, and the backend refuses them.
"""
from dataclasses import dataclass

OK = None  # marker: supported value


@dataclass(frozen=True)
class Option:
    name: str
    tab: str
    label: str
    values: tuple            # ((value, label, reason_or_None), …) or None for bool
    default: object
    help: str = ''
    kind: str = 'choice'     # choice | bool | int | items (AP item name -> count) | list (subset of values)
    minimum: int = 0
    maximum: int = 0
    supported_ints: tuple = ()
    experimental: tuple = ()  # supported values requiring an in-game pilot

    def supported(self, value):
        if self.kind in ('items', 'list'):
            return True
        if self.kind == 'bool':
            return dict(self.values)[value] is OK
        if self.kind == 'int':
            return value in self.supported_ints
        return any(v == value and reason is OK for v, _, reason in self.values)

    def reason(self, value):
        if self.kind in ('items', 'list'):
            return None
        if self.kind == 'bool':
            return dict(self.values).get(value)
        if self.kind == 'int':
            return None if value in self.supported_ints else 'Value differs from the vanilla game: no adapter.'
        for v, _, reason in self.values:
            if v == value:
                return reason
        return 'Unknown value.'

    def allowed(self):
        if self.kind == 'items':
            return ()
        if self.kind == 'list':
            return tuple(v for v, _, _ in self.values)
        if self.kind == 'bool':
            return (False, True)
        if self.kind == 'int':
            return tuple(range(self.minimum, self.maximum + 1))
        return tuple(v for v, _, _ in self.values)


NO_ADAPTER = 'No proven game adapter for this value.'
PILOT = ('Adapter built and checked statically; in-game behaviour still to be confirmed by a pilot. '
         'Every ticked category is shuffled together.')
NO_EVENT = 'Event or NPC: reward adapter still to be written and proven in game.'
GENERIC_KEYS = 'Remake keys are generic (credited to the current dungeon): impossible outside the dungeon.'
# Items that can be held from the start (silent pouch add at the end of the opening).
# Tunics, trade items and dungeon items have no pouch actor of their own yet.
STARTABLE_ITEMS = (
    'Kokiri Sword', 'Biggoron Sword', 'Deku Shield', 'Hylian Shield', 'Mirror Shield',
    'Slingshot', 'Bow', 'Boomerang', 'Progressive Hookshot', 'Megaton Hammer', 'Lens of Truth',
    'Bomb Bag', 'Bombchus (10)', 'Fire Arrows', 'Ice Arrows', 'Light Arrows', 'Dins Fire', 'Farores Wind', 'Nayrus Love',
    'Iron Boots', 'Hover Boots', 'Progressive Strength Upgrade', 'Progressive Scale', 'Progressive Wallet',
    'Deku Nut Capacity', 'Deku Stick Capacity', 'Magic Meter', 'Double Defense', 'Ocarina', 'Bottle',
    'Bottle with Milk', 'Zeldas Letter', 'Stone of Agony', 'Heart Container', 'Piece of Heart',
    'Gold Skulltula Token', 'Kokiri Emerald', 'Goron Ruby', 'Zora Sapphire', 'Forest Medallion',
    'Fire Medallion', 'Water Medallion', 'Spirit Medallion', 'Shadow Medallion', 'Light Medallion',
    'Zeldas Lullaby', 'Eponas Song', 'Sarias Song', 'Suns Song', 'Song of Time', 'Song of Storms',
    'Minuet of Forest', 'Bolero of Fire', 'Serenade of Water', 'Requiem of Spirit', 'Nocturne of Shadow',
    'Prelude of Light',
)
MAX_START_COUNT = 100
KEY_RING_DUNGEONS = ('Forest Temple', 'Fire Temple', 'Water Temple', 'Shadow Temple', 'Spirit Temple',
                     'Bottom of the Well', 'Gerudo Training Ground', 'Ganons Castle')

OPTIONS = [
    # ------------------------------------------------------------------ Logic
    Option('logic_rules', 'Logic', 'Logic rules',
           (('glitchless', 'Glitchless (AP glitchless)', OK),
            ('glitched', 'Glitched', 'The N64 glitched rules do not describe the remake.'),
            ('no_logic', 'No logic', 'Refused: may block the game.')), 'glitchless',
           'Built-in glitchless logic (remake world).'),
    Option('logic_tricks', 'Logic', 'Tricks',
           (('none', 'None (AP default)', OK),
            ('custom', 'Custom list', 'N64 tricks are not checked in the remake.')), 'none'),
    Option('accessibility', 'Logic', 'Accessibility',
           (('full', 'Every location reachable', OK),
            ('minimal', 'Only victory guaranteed', OK)), 'full',
           'Always checked by a second, independent solver after placement.'),
    Option('logic_no_night_tokens_without_suns_song', 'Logic',
           'Night skulltulas without Sun\'s Song out of logic',
           ((False, OK), (True, OK)), False, "Night skulltulas count only with the Ocarina and Sun's Song.",
           kind='bool'),
    # ------------------------------------------------------------------ World
    Option('open_kakariko', 'World', 'Kakariko gate',
           (('closed', 'Closed (Zelda\'s Letter)', OK), ('zelda', 'Open after the letter', NO_ADAPTER),
            ('open', 'Open', OK)), 'closed',
           'Open: the gate and the Death Mountain part of the Fire Stone quest start as after the '
           'guard read Zelda\'s Letter. The castle visit and the Door of Time quest are unchanged. '
           'The letter has no use left: with the quest rewards shuffled it leaves the item pool and '
           'Zelda gives a shuffled item instead. To be confirmed in game.', experimental=('open',)),
    Option('open_door_of_time', 'World', 'Door of Time open',
           ((False, OK), (True, OK)), False,
           'The Door of Time stands open and the sword can be pulled without the Spiritual Stones or '
           'the Song of Time. Zelda\'s escape still gives the Ocarina of Time and the Song of Time. '
           'To be confirmed in game.', kind='bool', experimental=(True,)),
    Option('door_of_time_requirement', 'World', 'Door of Time requirements',
           (('all', 'Ocarina + Song of Time + three stones', OK),
            ('vanilla', 'Ocarina + Song of Time + Ruby and Sapphire', OK),
            ('song', 'Ocarina + Song of Time', OK)), 'song',
           'Play the Song of Time with an ocarina at the door. Three stones also requires the Kokiri '
           'Emerald, Goron Ruby and Zora Sapphire; Ruby and Sapphire only requires the latter two. '
           'Door of Time open overrides this requirement. Independent of the stones for Zelda\'s escape. '
           'To be confirmed in game.', experimental=('all', 'vanilla', 'song')),
    Option('spiritual_stones', 'World', 'Require Spiritual Stones',
           (('door', 'Follow Door of Time requirements (legacy seed)', OK),
            ('all', 'Require all', OK), ('vanilla', 'Vanilla', OK)), 'all',
           'Which stones Zelda\'s escape asks for to give the Ocarina of Time and the Song of Time. '
           'Require all: the Kokiri Emerald, the Goron Ruby and the Zora Sapphire. Vanilla: the Goron Ruby '
           'and the Zora Sapphire only, as in the original game. Door of Time requirements are separate.'),
    Option('zora_fountain', 'World', 'King Zora',
           (('closed', 'Ruto\'s Letter required', OK), ('adult', 'Moved for adult', NO_ADAPTER),
            ('open', 'Always moved', OK)), 'closed',
           'Always moved: King Zora starts aside, so Zora\'s Fountain needs no Ruto\'s Letter, and no '
           'later scene moves him back. The letter can no longer be delivered, so it never turns into '
           'a bottle. To be confirmed in game.',
           experimental=('open',)),
    Option('gerudo_fortress', 'World', 'Gerudo Fortress',
           (('normal', 'Four carpenters', OK), ('fast', 'One carpenter', OK),
            ('open', 'Open', 'The Gerudo Membership Card is handed over by the rescue of the last '
             'carpenter: with every carpenter free from the start its check would be lost.')), 'normal',
           'One carpenter: the first carpenter freed, in any cell, ends the fortress and brings the '
           'rescue reward, then frees the remaining carpenters and opens every cell; the keys of the '
           'thieves not yet defeated lie in their cells. '
           'To be confirmed in game.', experimental=('fast',)),
    Option('open_gerudo_valley_bridge', 'World', 'Gerudo Valley bridge repaired',
           ((False, OK), (True, OK)), False,
           'The adult crosses the repaired Gerudo Valley bridge on foot from the start. '
           'The carpenters stay in their cells and the last rescue still '
           'brings the Gerudo Membership Card. To be confirmed in game.', kind='bool', experimental=(True,)),
    Option('starting_age', 'World', 'Starting age',
           (('child', 'Child', OK), ('adult', 'Adult', OK), ('random', 'Random', NO_ADAPTER)), 'child',
           'Adult: a new game begins as adult Link in the Temple of Time, with the Door of Time open '
           '(the "Door of Time open" option is forced on) and time travel possible both ways at the '
           'pedestal. Link holds the Master Sword (needed to travel back) and the starting inventory '
           'you choose, nothing else. New save required. To be confirmed in game.',
           experimental=('adult',)),
    # ------------------------------------------------------------------- Goal
    Option('bridge', 'Goal', 'Rainbow Bridge',
           (('vanilla', 'Shadow and Spirit medallions (vanilla)', OK), ('open', 'Open', NO_ADAPTER),
            ('stones', 'Stones', NO_ADAPTER), ('medallions', 'Medallions', NO_ADAPTER),
            ('dungeons', 'Dungeons', NO_ADAPTER), ('tokens', 'Skulltulas', NO_ADAPTER),
            ('hearts', 'Hearts', NO_ADAPTER)), 'vanilla'),
    Option('trials', 'Goal', 'Ganon\'s Castle trials', None, 6, kind='int',
           minimum=0, maximum=6, supported_ints=(6,), help='The remake keeps all six trials.'),
    Option('shuffle_ganon_bosskey', 'Goal', 'Ganon\'s Boss Key',
           (('vanilla', 'Vanilla', OK), ('remove', 'Removed', NO_ADAPTER), ('dungeon', 'In the castle', NO_ADAPTER),
            ('medallions', 'Medallions', NO_ADAPTER), ('stones', 'Stones', NO_ADAPTER),
            ('dungeons', 'Dungeons', NO_ADAPTER), ('tokens', 'Skulltulas', NO_ADAPTER)), 'vanilla'),
    Option('triforce_hunt', 'Goal', 'Triforce hunt', ((False, OK), (True, NO_ADAPTER)), False, kind='bool'),
    # ------------------------------------------------------------------ Items
    Option('blue_fire_arrows', 'Items', 'Ice arrows melt red ice',
           ((False, OK), (True, OK)), False,
           'Usable ice arrows melt red ice like bottled blue fire. Requires the bow and magic. '
           'To be confirmed in game.', kind='bool', experimental=(True,)),
    Option('shuffle_chests', 'Items', 'Content of every chest (major items included)',
           ((False, OK), (True, OK)), True, 'Drop__DropActor mechanism already validated in game on four chests.',
           kind='bool', experimental=(True,)),
    Option('chest_matching', 'Items', 'Remake ↔ AP chest matching',
           (('strict', 'Strict (safe)', OK), ('scene', 'By zone (heuristic)', OK)), 'strict',
           'Strict: progression only goes into identified chests. By zone: more chests, '
           'with the strictest access rule of the zone.', experimental=('scene',)),
    Option('shuffle_kokiri_sword', 'Items', 'Shuffle the Kokiri Sword', ((False, OK), (True, OK)), True,
           kind='bool', experimental=(True,)),
    Option('shuffle_remake_items', 'Items', 'Shuffle remake-only Deku seeds and jars',
           ((False, OK), (True, OK)), True, 'Items absent from the AP logic: moved as filler.', kind='bool'),
    Option('progressive_order', 'Items', 'Progressive items in order (hookshot before longshot…)',
           ((False, OK), (True, OK)), True,
           'Always the case: each copy found gives the level above the one held. No effect, kept for '
           'older settings.', kind='bool'),
    Option('progressive_strict', 'Items', 'Strict order: the higher level requires the previous one',
           ((False, OK), (True, OK)), False,
           'Always the case: a level is only given above the previous one. No effect, kept for older '
           'settings.', kind='bool'),
    Option('shuffle_song_items', 'Items', 'Songs',
           (('song', 'Vanilla', OK), ('shuffled', 'Shuffled among song locations', OK),
            ('dungeon', 'Song locations and dungeon rewards', OK),
            ('any', 'Anywhere a cutscene can give them', OK),
            ('everywhere', 'Anywhere, chests and pickups too', OK)), 'song',
           'A song is given with its text only ("You learned …"), nothing in Link\'s hands; '
           'the song cutscenes no longer teach their melody when they give another item. '
           '"Anywhere a cutscene": song locations, dungeon rewards, great fairies and story rewards (the '
           'matching options must be on). "Chests and pickups too": also chests, freestanding spots, '
           'pots, crates and gold skulltulas when those are shuffled; there the song shows Sheik\'s '
           'harp in its colour of the ocarina menu. Not validated in game.',
           experimental=('shuffled', 'dungeon', 'any', 'everywhere')),
    Option('shopsanity', 'Items', 'Shops (items shuffled per shop)',
           (('off', 'Vanilla', OK), ('1', '1 item per shop', OK), ('2', '2 items', OK),
            ('3', '3 items', OK), ('4', '4 items', OK), ('5', '5 items', OK), ('6', '6 items', OK),
            ('7', '7 items', OK), ('8', '8 items', OK), ('all', 'Whole shops (refills too)', OK),
            ('random', '1 to 4 random items', OK)), 'off',
           PILOT + ' Counted per shop (the Market bazaar, potion shop and bombchu shop are three shops). '
           'Fixed price of 10 rupees; a shuffled slot is sold once. From 1 to 8 items, one copy of each purchase '
           'the logic uses (shields, tunics, bottle refills, bombchus, nuts, sticks) stays on sale, so a shop may '
           'keep a few vanilla items. "Whole shops" shuffles every slot: the logic then counts on the world for '
           'refills (Blue Fire, bugs, fish, fairies, Deku Baba drops). Masks not included.',
           experimental=('1', '2', '3', '4', '5', '6', '7', '8', 'all', 'random')),
    Option('tokensanity', 'Items', 'Gold Skulltulas',
           (('off', 'Vanilla', OK), ('dungeons', 'Dungeons', OK), ('overworld', 'Overworld', OK),
            ('all', 'All', OK)), 'off',
           PILOT + ' The skulltula drops the placed item; tokens may come from other sources.',
           experimental=('dungeons', 'overworld', 'all')),
    Option('shuffle_scrubs', 'Items', 'Business Scrubs',
           (('off', 'Vanilla', OK), ('low', 'Low price (10 rupees)', OK), ('regular', 'Remake price', OK),
            ('random', 'Random prices (10 to 99 rupees)', OK)), 'off',
           PILOT + ' Single-sale remake scrubs: stick upgrade (Lost Woods bridge), nut upgrade '
           '(Lost Woods), field and crater heart pieces. "Remake price": 40 and 100 rupees '
           '(100 needs the Adult\'s Wallet). The scrub still announces its vanilla item; the item given '
           'is the placed one. Refill scrubs (3 items) and Dream World scrubs not included.',
           experimental=('low', 'regular', 'random')),
    Option('shuffle_cows', 'Items', 'Cows', ((False, OK), (True, NO_EVENT)), False, kind='bool'),
    Option('shuffle_ocarinas', 'Items', 'Ocarinas', ((False, OK), (True, NO_EVENT)), False, kind='bool'),
    Option('shuffle_child_trade', 'Items', 'Child trade quest',
           (('vanilla', 'Vanilla', OK), ('shuffle', 'Shuffled', NO_EVENT), ('skip_child_zelda', 'Skip Zelda', NO_EVENT)), 'vanilla'),
    Option('shuffle_master_sword', 'Items', 'Master Sword', ((False, OK), (True, OK)), False,
           'Shuffle the Master Sword and the reward at its pedestal. Time travel remains available '
           'at the pedestal. To be validated in game.', kind='bool', experimental=(True,)),
    Option('shuffle_gerudo_card', 'Items', 'Gerudo Membership Card', ((False, OK), (True, OK)), False,
           'Shuffle the Gerudo Membership Card and the reward for rescuing the carpenters. '
           'Rescuing the carpenters still completes their quest. The card grants membership, '
           'including before the rescues, for the gate, the training ground '
           'and horseback archery. To be validated in game.',
           kind='bool', experimental=(True,)),
    Option('shuffle_beans', 'Items', 'Magic beans', ((False, OK), (True, NO_EVENT)), False, kind='bool'),
    Option('shuffle_medigoron_carpet_salesman', 'Items', 'Medigoron and carpet salesman',
           ((False, OK), (True, NO_EVENT)), False, kind='bool'),
    Option('shuffle_freestanding_items', 'Items', 'Freestanding items (heart pieces, rupees, hearts)',
           (('off', 'Vanilla', OK), ('dungeons', 'Dungeons', OK), ('overworld', 'Overworld', OK),
            ('all', 'All', OK)), 'off', PILOT, experimental=('dungeons', 'overworld', 'all')),
    Option('shuffle_npc_gifts', 'Items', 'NPC gifts and minigames',
           ((False, OK), (True, OK)), False,
           PILOT + ' Out of scope: trades up to the Biggoron Sword, songs, boss rewards, '
           'child trade, cows, masks, great fairies.', kind='bool', experimental=(True,)),
    Option('shuffle_boss_rewards', 'Items', 'Bosses and dungeon rewards',
           ((False, OK), (True, OK)), False,
           'Spiritual stones, medallions (Rauru\'s included) and boss heart containers. Vanilla cutscene kept, only the item given changes. To be validated in game. '
           'The shuffled heart container is placed as soon as the boss room is entered.', kind='bool', experimental=(True,)),
    Option('shuffle_great_fairies', 'Items', 'Great Fairies',
           ((False, OK), (True, OK)), False,
           'Spells (Din, Farore, Nayru), magic, double magic and double defense. Vanilla cutscene kept, only the item given changes. To be validated in game.',
           kind='bool', experimental=(True,)),
    Option('shuffle_quest_rewards', 'Items', 'Quest rewards',
           ((False, OK), (True, OK)), False,
           'Fairy Ocarina (Saria), Ocarina of Time, Zelda\'s Letter, Light Arrows, Fire Arrows (Lake Hylia sun), Biggoron Sword, Ruto\'s Letter. '
           'Zelda\'s Letter stays Zelda\'s gift while the child trade quest is vanilla: it takes the '
           'Weird Egg\'s slot, and Talon could no longer be woken. '
           'Vanilla cutscene kept, only the item given changes. To be validated in game. Out of scope: trade items, songs.', kind='bool', experimental=(True,)),
    Option('shuffle_pots', 'Items', 'Pots (as checks)',
           (('off', 'Vanilla', OK), ('all', 'All', OK)), 'off',
           PILOT + ' Only pots with an explicit drop; a pot respawns as in the game; once its check is collected, it drops nothing more.',
           experimental=('all',)),
    Option('shuffle_crates', 'Items', 'Crates (as checks)',
           (('off', 'Vanilla', OK), ('all', 'All', OK)), 'off', PILOT, experimental=('all',)),
    Option('shuffle_beehives', 'Items', 'Beehives', ((False, OK), (True, OK)), False, PILOT, kind='bool',
           experimental=(True,)),
    Option('shuffle_bushes', 'Items', 'Bushes and grass (as checks)', ((False, OK), (True, OK)), False,
           PILOT + ' Only grass with an explicit drop; regrowing variants excluded.', kind='bool',
           experimental=(True,)),
    Option('shuffle_rocks', 'Items', 'Rocks and stones (as checks)', ((False, OK), (True, OK)), False,
           PILOT, kind='bool', experimental=(True,)),
    Option('shuffle_trees', 'Items', 'Trees (as checks)', ((False, OK), (True, OK)), False,
           PILOT + ' About 50 trees without a drop of their own (Hyrule Field, Kokiri Forest, castle, Kakariko): '
           'the first reward falls when Link rolls into the tree.', kind='bool', experimental=(True,)),
    Option('shuffle_frog_song_rupees', 'Items', 'Frog song rupees', ((False, OK), (True, NO_EVENT)), False, kind='bool'),
    Option('start_inventory_from_pool', 'Items', 'Starting inventory',
           None, {}, 'Items held from the start (copies taken out of the item pool). Hearts: '
           '"Heart Container" or "Piece of Heart"; songs by name ("Sarias Song"). Tunics are not available yet.', kind='items'),
    Option('item_pool_value', 'Items', 'Item pool',
           (('balanced', 'Balanced', OK), ('plentiful', 'Plentiful (one extra copy of the major items)', OK),
            ('scarce', 'Scarce (fewer bottles and hearts)', OK),
            ('minimal', 'Minimal (one bottle, no extra hearts)', OK)), 'balanced',
           'Applies to the shuffled locations only (their count never changes): extra copies '
           'replace rupees and other filler, removed copies become rupees.'),
    Option('fake_item_traps', 'Items', 'Fake item traps',
           (('none', 'None', OK), ('some', 'Some (one per major item)', OK),
            ('plentiful', 'Plentiful (two per major item, plus dungeon rewards and songs)', OK)), 'none',
           'Fake copies of items (hookshot, bow, boots…), in chests and on the ground (freestanding, '
           'skulltulas, pots, rocks…), never NPC gifts or shops. Some: one per major item of the pool. '
           'Plentiful: two per major item, plus one per medallion, spiritual stone and song. A trap looks '
           'like the real item, but its text says it is a trap and Link is frozen. Replaces filler. '
           'Not available for Archipelago. To be confirmed in game.',
           experimental=('some', 'plentiful')),
    # --------------------------------------------------------------- Dungeons
    Option('shuffle_mapcompass', 'Dungeons', 'Maps and compasses',
           (('vanilla', 'Vanilla', OK), ('dungeon', 'In their dungeon', OK), ('remove', 'Removed', OK),
            ('startwith', 'Start with', OK), ('any_dungeon', 'Any dungeon', OK),
            ('overworld', 'Overworld', OK), ('keysanity', 'Anywhere', OK)), 'dungeon',
           '"Start with": every map and compass is held from the start; their chests hold other items. '
           'Outside their dungeon, each map and compass becomes a dungeon-specific item ("Map: …").',
           experimental=('startwith', 'any_dungeon', 'overworld', 'keysanity')),
    Option('shuffle_smallkeys', 'Dungeons', 'Small keys',
           (('vanilla', 'Vanilla', OK),
            ('dungeon', 'In their dungeon (key rings)', OK),
            ('remove', 'Removed (all keys from the start)', OK),
            ('any_dungeon', 'Any dungeon (key rings)', OK), ('overworld', 'Overworld (key rings)', OK),
            ('keysanity', 'Anywhere (key rings)', OK)), 'vanilla',
           'Except for "Vanilla", small keys become one key ring per dungeon (Key rings option '
           '= All dungeons): remake keys are generic, only a dungeon-specific key ring '
           'can be placed elsewhere. Small key chests receive other items.',
           experimental=('dungeon', 'remove', 'any_dungeon', 'overworld', 'keysanity')),
    Option('shuffle_hideoutkeys', 'Dungeons', 'Gerudo hideout keys',
           (('vanilla', 'Guards', OK), ('overworld', 'Overworld', NO_EVENT), ('keysanity', 'Anywhere', NO_EVENT)), 'vanilla'),
    Option('shuffle_bosskeys', 'Dungeons', 'Boss keys',
           (('vanilla', 'Vanilla', OK), ('dungeon', 'In their dungeon', OK),
            ('remove', 'Removed (boss keys from the start)', OK),
            ('any_dungeon', 'Any dungeon', OK), ('keysanity', 'Anywhere', OK)), 'vanilla',
           'Outside their dungeon, each boss key becomes a dungeon-specific item ("Boss Key: …") '
           'that opens the boss door of that dungeon wherever it is found. Ganon\'s key: option of the Goal tab.',
           experimental=('dungeon', 'remove', 'any_dungeon', 'keysanity')),
    Option('key_rings', 'Dungeons', 'Key rings',
           (('off', 'None', OK), ('all', 'All dungeons', OK), ('choose', 'Chosen dungeons', OK),
            ('random', 'Random dungeons', OK)), 'off',
           'One key ring per dungeon (Forest, Fire, Water, Shadow, Spirit, Well, Gerudo Training Ground, Ganon\'s Castle): '
           'all its small keys at once, wherever it is found. Required as soon as small '
           'keys leave their place. With chosen or random dungeons, the other dungeons keep their '
           'small keys in place (remake keys are generic).', experimental=('all', 'choose', 'random')),
    Option('key_rings_list', 'Dungeons', 'Key ring dungeons',
           tuple((d, d, OK) for d in KEY_RING_DUNGEONS), (),
           'Dungeons with a key ring when "Key rings" is "Chosen dungeons".', kind='list'),
    Option('dungeon_shortcuts', 'Dungeons', 'Dungeon shortcuts', (('off', 'None', OK), ('all', 'All', NO_ADAPTER)), 'off'),
    # ------------------------------------------------------------------ Souls
    Option('shuffle_enemy_spawns', 'Souls', 'Enemy souls',
           (('off', 'Off', OK), ('bosses', 'Bosses only', OK), ('regional', 'One soul per region', OK),
            ('all', 'One soul per enemy type', OK)), 'off',
           'An enemy only appears once its soul is obtained (OoTR Dev-Rob). Logic: each dungeon or boss '
           'room requires the souls present there. A new save is required.',
           experimental=('bosses', 'regional', 'all')),
    # -------------------------------------------------------- Quality of life
    Option('skip_child_zelda', 'Quality of life', 'Skip child Hyrule Castle', ((False, OK), (True, OK)), False,
           'A new game starts as if Malon, Talon, Zelda and Impa had already been met: Zelda\'s Letter '
           'and Zelda\'s Lullaby are shuffled elsewhere (the lullaby anywhere a song can be given). '
           'The castle grounds become optional: every '
           'shuffled check there (pots, crates, skulltulas, Zelda, Impa) holds a green rupee, except the '
           'Great Fairy. What comes after the castle keeps its own conditions (Kokiri Forest exit after '
           'the Deku Tree, Kakariko gate with the letter...). New save required. To be validated in game.',
           kind='bool', experimental=(True,)),
    Option('no_escape_sequence', 'Quality of life', 'Skip the castle escape', ((False, OK), (True, NO_EVENT)), False, kind='bool'),
    Option('no_guard_stealth', 'Quality of life', 'Skip the castle stealth section', ((False, OK), (True, NO_EVENT)), False, kind='bool'),
    Option('no_epona_race', 'Quality of life', 'Epona without the race', ((False, OK), (True, NO_EVENT)), False, kind='bool'),
    Option('fast_chests', 'Quality of life', 'Fast chest opening', ((False, OK), (True, OK)), False,
           'Same patch as "Chests without cutscene" in the setup: the lid opens and Link holds the item up.',
           kind='bool'),
    Option('free_scarecrow', 'Quality of life', 'Free scarecrow', ((False, OK), (True, NO_EVENT)), False, kind='bool'),
    Option('big_poe_count', 'Quality of life', 'Big Poes to bring back', None, 10,
           'The collector gives his reward after this many Big Poes. Not validated in game.',
           kind='int', minimum=1, maximum=10, supported_ints=tuple(range(1, 11)), experimental=tuple(range(1, 10))),
    Option('chicken_count', 'Quality of life', 'Cuccos to bring back', None, 7,
           'The cucco lady in Kakariko gives her reward after this many cuccos. Not validated in game.',
           kind='int', minimum=0, maximum=7, supported_ints=tuple(range(1, 8)), experimental=tuple(range(1, 7))),
]
BY_NAME = {option.name: option for option in OPTIONS}
TABS = ('Logic', 'World', 'Goal', 'Items', 'Dungeons', 'Souls', 'Quality of life')
OUT_OF_SCOPE = ('Entrance shuffle, Master Quest, multiworld and gossip stone hints: out of scope '
                'for this version, AP default values enforced (no shuffling).')


# Options added after a release, left out of the stored settings at this value: stored settings
# without the option mean it, and seeds made before the option keep their identity.
UNRECORDED = {'spiritual_stones': 'all', 'door_of_time_requirement': 'song', 'blue_fire_arrows': False,
              'fake_item_traps': 'none'}


def recorded(values):
    """``values`` without the options at their unrecorded value: what a seed stores and hashes."""
    return {name: value for name, value in values.items() if UNRECORDED.get(name) != value}


def stored_value(values, name):
    """Option ``name`` in stored settings (``recorded``, so it may be missing)."""
    return values.get(name, UNRECORDED.get(name, BY_NAME[name].default))


def escape_requirement(values):
    """Independent escape choice; linked older seeds retain their original rules."""
    value = stored_value(values, 'spiritual_stones')
    return stored_value(values, 'door_of_time_requirement') if value == 'door' else value


def defaults():
    return {option.name: (dict(option.default) if isinstance(option.default, dict) else option.default)
            for option in OPTIONS}


def parse_items(text):
    """``"Hover Boots, Progressive Hookshot x2"`` → ``{'Hover Boots': 1, 'Progressive Hookshot': 2}``."""
    import re
    result = {}
    for part in (p.strip() for p in str(text).replace(';', ',').split(',')):
        if not part:
            continue
        match = re.fullmatch(r'(.+?)\s*(?:[x×*]\s*(\d+))?', part, re.IGNORECASE)
        name, count = match.group(1).strip(), int(match.group(2) or 1)
        canonical = next((i for i in STARTABLE_ITEMS if i.casefold() == name.casefold()), None)
        if canonical is None:
            raise ValueError(f'Unknown or unavailable starting item: {name}')
        result[canonical] = result.get(canonical, 0) + count
    return result


def format_items(items):
    return ', '.join(name if count == 1 else f'{name} x{count}' for name, count in sorted(items.items()))


def validate(values, supported_only=False):
    if not isinstance(values, dict):
        raise ValueError('Invalid full randomizer options.')
    unknown = set(values) - set(BY_NAME)
    if unknown:
        raise ValueError('Unknown options: ' + ', '.join(sorted(unknown)))
    result = defaults()
    result.update(values)
    for name, value in result.items():
        option = BY_NAME[name]
        if option.kind == 'list':
            if (not isinstance(value, (list, tuple)) or len(set(value)) != len(value)
                    or not set(value) <= set(option.allowed())):
                raise ValueError(f'{name}: unknown or duplicate value.')
            result[name] = tuple(v for v in option.allowed() if v in value)
        elif option.kind == 'items':
            if (not isinstance(value, dict) or any(item not in STARTABLE_ITEMS for item in value)
                    or any(type(n) is not int or not 1 <= n <= MAX_START_COUNT for n in value.values())):
                raise ValueError(f'{name}: unknown item or invalid count.')
            result[name] = dict(sorted(value.items()))
        elif option.kind == 'bool':
            if type(value) is not bool:
                raise ValueError(f'{name} must be a boolean.')
        elif option.kind == 'int':
            if type(value) is not int or not option.minimum <= value <= option.maximum:
                raise ValueError(f'{name} must be an integer between {option.minimum} and {option.maximum}.')
        elif value not in option.allowed():
            raise ValueError(f'Unknown value for {name}: {value!r}')
        if supported_only and not option.supported(value):
            raise ValueError(f'{option.label} = {value!r}: {option.reason(value)}')
    if result['starting_age'] == 'adult':
        result['open_door_of_time'] = True   # the adult starts beyond the door: it stands open
    if supported_only:
        moved = result['shuffle_smallkeys'] not in ('vanilla', 'remove')
        if moved and result['key_rings'] == 'off':
            raise ValueError('Small keys out of their place: set "Key rings" (remake keys are generic).')
        if result['key_rings'] != 'off' and not moved:
            raise ValueError('Key rings: choose where the small keys go (not "Vanilla").')
        if result['key_rings'] == 'choose' and not result['key_rings_list']:
            raise ValueError('Key rings: choose at least one dungeon.')
    return result


def experimental_choices(values):
    return sorted(f'{BY_NAME[n].label} = {v}' for n, v in values.items() if v in BY_NAME[n].experimental)


PRESETS = {
    'ap_defaults': {'label': 'AP glitchless — defaults', 'values': {}},
    'everything': {'label': 'Everything shuffled (available values)', 'values': {
        'shuffle_chests': True, 'shuffle_kokiri_sword': True, 'shuffle_remake_items': True,
        'shuffle_mapcompass': 'dungeon', 'shuffle_smallkeys': 'keysanity', 'key_rings': 'all', 'shuffle_bosskeys': 'keysanity',
        'shuffle_enemy_spawns': 'all', 'chest_matching': 'scene', 'progressive_order': True,
        'tokensanity': 'all', 'shopsanity': '4', 'shuffle_freestanding_items': 'all', 'shuffle_npc_gifts': True,
        'shuffle_boss_rewards': True, 'shuffle_great_fairies': True, 'shuffle_quest_rewards': True,
        'shuffle_master_sword': True, 'shuffle_gerudo_card': True,
        'shuffle_song_items': 'everywhere', 'blue_fire_arrows': True,
        'shuffle_pots': 'all', 'shuffle_crates': 'all', 'shuffle_beehives': True, 'shuffle_bushes': True,
        'shuffle_rocks': True, 'shuffle_trees': True, 'shuffle_scrubs': 'low'}},
    'prudent': {'label': 'Prudent (chests except keys, no souls)', 'values': {
        'shuffle_chests': True, 'shuffle_kokiri_sword': False, 'shuffle_mapcompass': 'vanilla',
        'shuffle_smallkeys': 'vanilla', 'shuffle_bosskeys': 'vanilla', 'shuffle_enemy_spawns': 'off'}},
}


def preset(name):
    values = defaults()
    values.update(PRESETS[name]['values'])
    return values


def from_ap_yaml(text):
    """Import the options of an AP YAML. Returns (values, ignored_messages).

    Reads an ``OoT Remake`` YAML (game section ``OoT Remake``, application-only
    options under ``OoT Remake application``) or an original Ocarina of Time one
    (section ``Ocarina of Time``, remake extras under ``OoT Remake``).
    """
    try:
        import yaml
    except ImportError as error:
        raise ValueError('PyYAML is needed to import an Archipelago YAML.') from error
    document = yaml.safe_load(text)
    if not isinstance(document, dict):
        raise ValueError('Invalid Archipelago YAML.')
    original = document.get('Ocarina of Time') or document.get('oot')
    remake = document.get(AP_GAME)
    if isinstance(remake, dict) and (document.get('game') == AP_GAME or not isinstance(original, dict)):
        section, extra = remake, document.get(AP_APP_SECTION)
    elif isinstance(original, dict):
        section, extra = original, remake
    else:
        raise ValueError(f'"{AP_GAME}" section missing from the YAML.')
    values, ignored = defaults(), []
    items = list(section.items()) + (list(extra.items()) if isinstance(extra, dict) else [])
    for key, raw in items:
        if key == 'open_forest':
            if section is not remake:
                ignored.append('open_forest: set by "Open the way" in the setup')
            continue
        if raw == 'randomized' and key in BY_NAME and 'random' in BY_NAME[key].allowed():
            raw = 'random'  # Archipelago's name of the remake's own random value
        if key == 'start_inventory':
            key = 'start_inventory_from_pool'
        if key not in BY_NAME:
            ignored.append(f'{key}: option not carried over in this version')
            continue
        if BY_NAME[key].kind == 'list':
            raw = list(raw) if isinstance(raw, (list, tuple, set, dict)) else []
            kept = [v for v in raw if v in BY_NAME[key].allowed()]
            ignored.extend(f'{key}: unknown dungeon {v!r}' for v in raw if v not in kept)
            values[key] = tuple(v for v in BY_NAME[key].allowed() if v in kept)
            continue
        if BY_NAME[key].kind == 'items':
            kept = {}
            for item, count in (raw or {}).items() if isinstance(raw, dict) else ():
                if item in STARTABLE_ITEMS and type(count) is int and 1 <= count <= MAX_START_COUNT:
                    kept[item] = kept.get(item, 0) + count
                else:
                    ignored.append(f'{key}: {item} not available as a starting item')
            values[key] = dict(sorted(kept.items()))
            continue
        if isinstance(raw, dict):
            weighted = [(k, w) for k, w in raw.items() if isinstance(w, (int, float)) and w > 0]
            if len(weighted) != 1:
                ignored.append(f'{key}: several weighted values not supported')
                continue
            raw = weighted[0][0]
        option = BY_NAME[key]
        if option.kind == 'bool':
            raw = raw if isinstance(raw, bool) else str(raw).lower() in ('true', 'on', '1')
        elif option.kind == 'int':
            try:
                raw = int(raw)
            except (TypeError, ValueError):
                ignored.append(f'{key}: integer expected')
                continue
        elif key == 'logic_tricks':
            raw = 'none' if not raw else 'custom'
        elif isinstance(raw, bool):
            # YAML 1.1 reads ``off``/``on`` as booleans.
            raw = 'off' if raw is False else 'on'
        elif isinstance(raw, int):
            raw = str(raw)
        if raw not in option.allowed():
            ignored.append(f'{key}: unknown value {raw!r}')
            continue
        values[key] = raw
        if not option.supported(raw):
            ignored.append(f'{key} = {raw!r}: {option.reason(raw)}')
    return values, ignored


REMAKE_ONLY = ('shuffle_chests', 'chest_matching', 'shuffle_remake_items', 'progressive_order',
               'progressive_strict', 'shuffle_enemy_spawns', 'shuffle_npc_gifts', 'shuffle_bushes', 'shuffle_rocks', 'shuffle_trees',
               'shuffle_boss_rewards', 'shuffle_great_fairies', 'shuffle_quest_rewards')


AP_GAME = 'OoT Remake'
AP_APP_SECTION = 'OoT Remake application'


# Randomization tab: each category checkbox drives these complete-mode options
# ((option, value when checked, value when unchecked), …). Categories absent
# here have no proven adapter and stay greyed in complete mode.
CATEGORY_OPTIONS = {
    'world_chests': (('shuffle_chests', True, False),),
    'pots': (('shuffle_pots', 'all', 'off'),),
    'bushes': (('shuffle_bushes', True, False),),
    'crates': (('shuffle_crates', 'all', 'off'),),
    'rocks': (('shuffle_rocks', True, False),),
    'trees': (('shuffle_trees', True, False),),
    'beehives': (('shuffle_beehives', True, False),),
    'npc_gifts': (('shuffle_npc_gifts', True, False),),
    'minigames': (('shuffle_npc_gifts', True, False),),
    'quest_rewards': (('shuffle_quest_rewards', True, False),),
    'boss_rewards': (('shuffle_boss_rewards', True, False),),
    'fairies': (('shuffle_great_fairies', True, False),),
    'skulltulas': (('tokensanity', 'all', 'off'),),
    'shops': (('shopsanity', '4', 'off'),),
    'loose_items': (('shuffle_freestanding_items', 'all', 'off'),),
    'dungeon_items': (('shuffle_mapcompass', 'dungeon', 'vanilla'), ('shuffle_bosskeys', 'dungeon', 'vanilla')),
    'scrubs': (('shuffle_scrubs', 'low', 'off'),),
}


def category_checked(values, category):
    return any(values[option] != off for option, _, off in CATEGORY_OPTIONS[category])


def set_category(values, category, checked):
    """Return a copy of ``values`` with the options of ``category`` switched."""
    result = dict(values)
    for option, on, off in CATEGORY_OPTIONS[category]:
        result[option] = on if checked else off
    return result


def ap_settings(options, open_forest):
    """Settings of the AP rules (``logic.rules.Logic``) for remake options ``options``."""
    values = {name: options[name] for name in ('open_kakariko', 'open_door_of_time', 'door_of_time_requirement', 'zora_fountain',
                                               'spiritual_stones', 'gerudo_fortress', 'open_gerudo_valley_bridge',
                                               'starting_age', 'bridge', 'trials',
                                               'shuffle_ganon_bosskey', 'big_poe_count', 'chicken_count',
                                               'free_scarecrow', 'shuffle_child_trade', 'logic_rules',
                                               'shuffle_master_sword', 'shuffle_gerudo_card',
                                               'logic_no_night_tokens_without_suns_song',
                                               'skip_child_zelda')}
    values['open_forest'] = 'closed_deku' if open_forest else 'closed'
    # AP rules' ``keysanity``: false lets one Fire Temple door open without its key
    # ("Fire Temple Lower Locked Door": (Small Key, 8) or not keysanity), OoTR's
    # "a vanilla key may sit behind its own door". Shuffled small keys are key rings
    # here (one item, every key at once): the ring itself could go behind that door
    # (Discord 16/11: Fire Temple ring on Volvagia, boss key chest past the door).
    values['keysanity'] = options.get('shuffle_smallkeys', 'vanilla') != 'vanilla'
    return values
