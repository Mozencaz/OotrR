
"""Enemy soul families, soul items and the names of their generated actors and events.

The files that give a soul are built by ``patching/soul_adapter.py``.
"""
# (family id, French label, Gyaml prefixes, boss room AP region or None)
FAMILIES = [
    ('Stalfos', 'Stalfos', ('Enemy_Stalfos',), None),
    ('Octorok', 'Octorok', ('Enemy_Octorok',), None),
    ('BigOcto', 'Gros Octorok', ('Enemy_MiddleBoss_BigOcto',), None),
    ('Wallmaster', 'Main Mortelle', ('Enemy_Wallmaster',), None),
    ('Floormaster', 'Main Mortelle au sol', ('Enemy_Floormaster',), None),
    ('Dodongo', 'Dodongo', ('Enemy_Dodongo',), None),
    ('BabyDodongo', 'Bébé Dodongo', ('Enemy_BabyDodongo',), None),
    ('Keese', 'Keese', ('Enemy_Keese',), None),
    ('Tektite', 'Araknon', ('Enemy_Tektite',), None),
    ('Peahat', 'Pihat', ('Enemy_Peahat',), None),
    ('Lizalfos', 'Lézalfos et Dinolfos', ('Enemy_Lizalfos', 'Enemy_MiddleBoss_Lizalfos', 'Enemy_Dinolfos'), None),
    ('GohmaLarva', 'Larves de Gohma', ('Enemy_Gohma_Larva', 'Enemy_Gohma_Egg'), None),
    ('Shabom', 'Shabom', ('Enemy_Shabom',), None),
    ('BiriBari', 'Biri et Bari', ('Enemy_Biri', 'Enemy_Bari'), None),
    ('Tailpasaran', 'Tailpasaran', ('Enemy_Tailpasaran',), None),
    ('TorchSlug', 'Limace de feu', ('Enemy_TorchSlug',), None),
    ('Skulltula', 'Skulltula', ('Enemy_Skulltula',), None),
    ('Skullwalltula', 'Skullwalltula', ('Enemy_Skullwalltula',), None),
    ('Moblin', 'Moblin', ('Enemy_Moblin',), None),
    ('Armos', 'Armos', ('Enemy_Amos',), None),
    ('Beamos', 'Beamos', ('Enemy_Beamos',), None),
    ('DekuBaba', 'Baba Mojo', ('Enemy_Dekubaba',), None),
    ('DekuScrub', 'Peste Mojo', ('Enemy_Scrub_Deku', 'Enemy_Scrub_Mad'), None),
    ('Bubble', 'Bubble', ('Enemy_Bubble',), None),
    ('ReDead', 'ReDead et Gibdo', ('Enemy_ReDead', 'Enemy_Gibdo'), None),
    ('DeadHand', 'Main Morte', ('Enemy_DeadHand',), None),
    ('FlareDancer', 'Danse-Flamme', ('Enemy_MiddleBoss_FlareDancer',), None),
    ('ShellBlade', 'Coquillame', ('Enemy_ShellBlade',), None),
    ('LikeLike', 'Like Like', ('Enemy_LikeLike',), None),
    ('Spike', 'Hérisson', ('Enemy_Spike',), None),
    ('Anubis', 'Anubis', ('Enemy_Anubis',), None),
    ('IronKnuckle', 'Hache-Viande', ('Enemy_IronKnuckle',), None),
    ('FlyingPot', 'Jarre volante', ('Enemy_FlyingPot',), None),
    ('Freezard', 'Freezard', ('Enemy_Freezard',), None),
    ('Stinger', 'Raie', ('Enemy_Stinger',), None),
    ('Wolfos', 'Wolfos', ('Enemy_Wolfos',), None),
    ('Guay', 'Guay', ('Enemy_Guay', 'Enemy_FlockGuayManager'), None),
    ('JabuTentacle', 'Tentacules de Jabu', ('Enemy_Tentacle',), None),
    ('DarkLink', 'Link Noir', ('Enemy_MiddleBoss_DarkLink',), None),
    ('Gohma', 'Reine Gohma', ('Enemy_DungeonBoss_Gohma',), 'Queen Gohma Boss Room'),
    ('KingDodongo', 'King Dodongo', ('Enemy_DungeonBoss_Dodongo',), 'King Dodongo Boss Room'),
    ('Barinade', 'Barinade', ('Enemy_DungeonBoss_Barinade',), 'Barinade Boss Room'),
    ('PhantomGanon', 'Ganon Spectral', ('Enemy_DungeonBoss_PhantomGanon',), 'Phantom Ganon Boss Room'),
    ('Volvagia', 'Volvagia', ('Enemy_DungeonBoss_Volvagia',), 'Volvagia Boss Room'),
    ('Morpha', 'Morpha', ('Enemy_DungeonBoss_Morpha',), 'Morpha Boss Room'),
    ('BongoBongo', 'Bongo Bongo', ('Enemy_DungeonBoss_BongoBongo',), 'Bongo Bongo Boss Room'),
    ('Twinrova', 'Twinrova', ('Enemy_DungeonBoss_Twinrova', 'Enemy_DungeonBoss_Kotake',
                              'Enemy_DungeonBoss_Koume', 'Enemy_KotakeKoumeBattleManager'), 'Twinrova Boss Room'),
]
BY_ID = {family: (label, prefixes, boss) for family, label, prefixes, boss in FAMILIES}
EXCLUDED_MARKERS = ('_Dictionary', 'Haribote', 'ClimaxOnly', 'GhostPicturePerformer', 'Skulltula_Gold',
                    'Scrub_Business', 'Scrub_ForestStage', 'IronKnuckle_Nabooru', 'SkullKid', 'Poe',
                    'Stalchild', 'Leever', 'GerudoThief', 'Ganon', 'CrazyFloorTile', 'TrickyDoor')
EXCLUDED_FOLDERS = ('DreamWorld', 'GanonCastle')
# French in-game names (EUfr / CAfr message files); FAMILIES labels are French too.
REGION_LABELS = {
    'InsideTheDekuTree': 'Arbre Mojo', 'DodongoCavern': 'Caverne Dodongo', 'InsideJabuJabuBelly': 'Jabu-Jabu',
    'ForestTemple': 'Temple de la Forêt', 'FireTemple': 'Temple du Feu', 'WaterTemple': 'Temple de l’Eau',
    'ShadowTemple': 'Temple de l’Ombre', 'SpiritTemple': 'Temple de l’Esprit', 'BottomOfTheWell': 'Puits',
    'IceCavern': 'Caverne Polaire', 'GerudoTrainingGround': 'Gymnase Gerudo', 'InsideGanonCastle': 'Château de Ganon',
    'KokiriForest': 'Forêt Kokiri', 'LostWood': 'Bois Perdus', 'SacredForestMeadow': 'Bosquet sacré',
    'HyruleField': 'Plaine d’Hyrule', 'Market': 'Bourg', 'HyruleCastle': 'Château d’Hyrule',
    'Graveyard': 'Cimetière', 'DeathMountainTrail': 'Mont du Péril', 'DeathMountainCrater': 'Cratère',
    'ZoraRiver': 'Rivière Zora', 'ZoraFountain': 'Fontaine Zora', 'GerudoValley': 'Vallée Gerudo',
    'GerudoFortress': 'Forteresse Gerudo', 'HountedWasteland': 'Désert hanté', 'DesertColossus': 'Colosse',
    'LakeHylia': 'Lac Hylia', 'KakarikoVillage': 'Cocorico', 'GoronCity': 'Village Goron', 'ZoraDomain': 'Domaine Zora',
}
LOCATION_KEYWORDS = {'Wolfos': 'Wolfos', 'Redead': 'ReDead', 'Moblin': 'Moblin', 'Octorok': 'Octorok',
                     'Tektite': 'Tektite', 'Deku Baba': 'DekuBaba', 'Dodongo': 'Dodongo', 'Peahat': 'Peahat',
                     'Target in Woods': 'DekuScrub'}
FLAG_PREFIX = 'IsGet.'
# Exceptions to EXCLUDED_MARKERS: Phantom Ganon himself carries the 'Ganon' marker
# that keeps Ganondorf and Ganon (the final fights) out. His painting performers
# (``GhostPicturePerformer``) and dictionaries stay excluded.
EXCLUDED_EXCEPTIONS = ('Enemy_DungeonBoss_PhantomGanon',)


def family_of(actor):
    if actor not in EXCLUDED_EXCEPTIONS and any(marker in actor for marker in EXCLUDED_MARKERS):
        return None
    best = None
    for family, _, prefixes, _ in FAMILIES:
        for prefix in prefixes:
            if (actor == prefix or actor.startswith(prefix + '_')) and (best is None or len(prefix) > best[1]):
                best = (family, len(prefix))
    return best[0] if best else None


def soul_item(key):
    return f'Soul ({key})'


# Generated actor names stay within the length seen working in game (13/11: 25
# characters handed over, 30 and 33 crashed the item get): regional souls use a
# short region code.
MAX_ACTOR_NAME = 25
REGION_CODES = {'BottomOfTheWell': 'Well', 'DeathMountainCrater': 'DMCrater', 'DeathMountainTrail': 'DMTrail',
                'DesertColossus': 'Colossus', 'GerudoFortress': 'GFortress', 'GerudoTrainingGround': 'GTG',
                'InsideGanonCastle': 'GanonCastle', 'InsideJabuJabuBelly': 'JabuJabu',
                'InsideTheDekuTree': 'DekuTree', 'SacredForestMeadow': 'SFMeadow',
                'KakarikoVillage': 'Kakariko', 'HountedWasteland': 'Wasteland'}


def soul_actor(item):
    key = item[len('Soul ('):-1]
    if key.startswith('Region:'):
        folder = key[len('Region:'):]
        return 'Item_Soul_R_' + REGION_CODES.get(folder, folder)
    return 'Item_Soul_' + key


def soul_label(item):
    return 'Soul: ' + soul_name(item, False)


def _spaced(name):
    return ''.join(' ' + c if c.isupper() and i else c for i, c in enumerate(name))


def soul_name(item, french=True):
    """Display name of the soul (without the "Soul" prefix)."""
    key = item[len('Soul ('):-1]
    if key.startswith('Region:'):
        folder = key[7:]
        return REGION_LABELS.get(folder, folder) if french else ENGLISH_REGIONS.get(folder, _spaced(folder))
    return BY_ID[key][0] if french else ENGLISH_FAMILIES.get(key, _spaced(key))


ENGLISH_FAMILIES = {'BigOcto': 'Big Octo', 'Wallmaster': 'Wallmaster', 'Floormaster': 'Floormaster',
                    'BabyDodongo': 'Baby Dodongo', 'Lizalfos': 'Lizalfos and Dinolfos',
                    'GohmaLarva': 'Gohma Larva', 'BiriBari': 'Biri and Bari', 'TorchSlug': 'Torch Slug',
                    'DekuBaba': 'Deku Baba', 'DekuScrub': 'Deku Scrub', 'ReDead': 'ReDead and Gibdo',
                    'DeadHand': 'Dead Hand', 'FlareDancer': 'Flare Dancer', 'ShellBlade': 'Shell Blade',
                    'LikeLike': 'Like Like', 'IronKnuckle': 'Iron Knuckle', 'FlyingPot': 'Flying Pot',
                    'JabuTentacle': 'Jabu-Jabu Tentacles', 'DarkLink': 'Dark Link', 'Gohma': 'Queen Gohma',
                    'KingDodongo': 'King Dodongo', 'PhantomGanon': 'Phantom Ganon', 'BongoBongo': 'Bongo Bongo'}
ENGLISH_REGIONS = {'InsideTheDekuTree': 'Deku Tree', 'DodongoCavern': "Dodongo's Cavern",
                   'InsideJabuJabuBelly': "Jabu-Jabu's Belly", 'BottomOfTheWell': 'Bottom of the Well',
                   'InsideGanonCastle': "Ganon's Castle", 'LostWood': 'Lost Woods',
                   'HountedWasteland': 'Haunted Wasteland', 'Market': 'Market', 'ZoraRiver': "Zora's River",
                   'ZoraFountain': "Zora's Fountain", 'ZoraDomain': "Zora's Domain"}


def soul_event_name(actor):
    return 'RandoSoul_' + actor[len('Item_Soul_'):] + '.event.root'


def soul_event_member(actor):
    """Pack member of the soul's get event (beside its actor parameters)."""
    return 'AI/' + soul_event_name(actor) + '.ainb'


def soul_event_ain(actor):
    return 'Work/AI/Root/Event/' + soul_event_name(actor) + '.ain'
