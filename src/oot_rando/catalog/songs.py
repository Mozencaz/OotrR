
"""Songs as items: their actors and the cutscenes that teach them.

The song shuffle itself is ``patching/song_adapter.py``.
"""
# AP song item -> (remake actor, MelodyType of Dm_SY_Ocarina).
SONGS = {
    'Zeldas Lullaby': ('Item_Melody_ZeldaLullaby', 0), 'Eponas Song': ('Item_Melody_EponaSong', 1),
    'Sarias Song': ('Item_Melody_SariaSong', 2), 'Suns Song': ('Item_Melody_SunSong', 3),
    'Song of Time': ('Item_Melody_TimeSong', 4), 'Song of Storms': ('Item_Melody_StormSong', 5),
    'Minuet of Forest': ('Item_Melody_ForestMinuet', 6), 'Bolero of Fire': ('Item_Melody_FireBolero', 7),
    'Serenade of Water': ('Item_Melody_WaterSerenade', 8), 'Requiem of Spirit': ('Item_Melody_SpiritRequiem', 9),
    'Nocturne of Shadow': ('Item_Melody_ShadowNocturne', 10), 'Prelude of Light': ('Item_Melody_LightPrelude', 11),
}
SONG_ACTOR_ITEMS = {actor: item for item, (actor, _) in SONGS.items()}
MELODY_PREFIX = 'Item_Melody_'
# Song locations: (AP location, give flow, give event, vanilla actor, teaching flows; None: the give flow).
SONG_LOCATIONS = (
    ('Song from Impa', 'Dm_MelodyGet_Zelda', 'Event111', 'Item_Melody_ZeldaLullaby', None),
    ('Song from Malon', 'Dm_MelodyGet_Epona', 'Event11', 'Item_Melody_EponaSong', None),
    ('Song from Saria', 'Dm_MelodyGet_Saria', 'Event109', 'Item_Melody_SariaSong', None),
    ('Song from Royal Familys Tomb', 'Dm_MelodyGet_Sun_03', 'Event34', 'Item_Melody_SunSong', ('Dm_MelodyGet_Sun',)),
    ('Song from Ocarina of Time', 'Dm_MelodyGet_Time', 'Event4', 'Item_Melody_TimeSong', None),
    ('Song from Windmill', 'Dm_MelodyGet_Storm', 'Event29', 'Item_Melody_StormSong', None),
    ('Sheik in Forest', 'Dm_MelodyGet_Forest', 'Event22', 'Item_Melody_ForestMinuet', None),
    ('Sheik in Crater', 'Dm_MelodyGet_Fire', 'Event192', 'Item_Melody_FireBolero', None),
    ('Sheik in Ice Cavern', 'Dm_MelodyGet_Water', 'Event29', 'Item_Melody_WaterSerenade', None),
    ('Sheik at Colossus', 'Dm_MelodyGet_Spilit', 'Event17', 'Item_Melody_SpiritRequiem', None),
    ('Sheik in Kakariko', 'Dm_MelodyGet_Shadow', 'Event21', 'Item_Melody_ShadowNocturne', None),
    ('Sheik at Temple', 'Dm_MelodyGet_Shine', 'Event53', 'Item_Melody_LightPrelude', None),
)


def is_song_actor(actor):
    return isinstance(actor, str) and actor.startswith(MELODY_PREFIX)


def song_gifts():
    """Song locations in the ``EVENT_GIFTS`` format of ``extra_sources``."""
    return tuple(('song', (ap,), (), ((stem, event, actor),)) for ap, stem, event, actor, _ in SONG_LOCATIONS)
