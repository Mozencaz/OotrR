"""Explicit coverage registry. A requested category is not an implemented adapter."""
CATEGORIES = {
    'world_chests': 'Ordinary rupee chests',
    'pots': 'Pots and jars',
    'trees': 'Reward trees',
    'bushes': 'Bushes and grass',
    'crates': 'Crates',
    'rocks': 'Rocks and stones',
    'beehives': 'Beehives',
    'quest_rewards': 'Quest rewards',
    'npc_gifts': 'NPC gifts',
    'songs': 'Songs',
    'boss_rewards': 'Bosses and dungeon rewards',
    'dungeon_items': 'Keys, maps and compasses',
    'skulltulas': 'Skulltulas and token rewards',
    'shops': 'Shops',
    'scrubs': 'Business Scrubs',
    'cows': 'Cows',
    'fairies': 'Fairies and Great Fairies',
    'loose_items': 'Freestanding items',
    'enemies': 'Enemy drops',
    'minigames': 'Minigames and fishing',
    'trades': 'Trades',
    'other_sources': 'Other reward sources',
}


def candidate_category(actor):
    """Inventory hints only; do not infer eligibility or a collection flag."""
    name = actor.get('Gyaml', '')
    if name.startswith('Obj_TBox') and 'Drop__DropActor' in actor.get('Dynamic', {}):
        return 'world_chests'
    for prefixes, category in (
        (('Obj_Pot_',), 'pots'),
        (('Obj_Plant_Grass', 'Land_kokiri_Plant_A_02'), 'bushes'),
        (('Obj_Tree', 'Land_Tree'), 'trees'),
        (('Obj_BrokenBox', 'Obj_WoodBox', 'Obj_Box', 'Obj_Crate'), 'crates'),
        (('Obj_BrokenRock', 'Obj_LiftRock', 'Obj_Rock', 'Obj_Stone'), 'rocks'),
        (('Obj_Kokiri_Beehive', 'Obj_Bee', 'Obj_Beehive'), 'beehives'),
        (('Shop_',), 'shops'),
        (('Npc_',), 'npc_gifts'),
        (('Enemy_',), 'enemies'),
        (('Item_',), 'loose_items'),
    ):
        if name.startswith(prefixes):
            if category == 'enemies' and any('ScrubBusiness_ShopItemActorName' in key for key in actor.get('Dynamic', {})):
                return 'scrubs'
            return category
    return 'other_sources'
