
"""Progressive families and the names of their token actors (``Item_Prog_<code>_<n>``).

The patch that converts a token into the next level is ``patching/progressive.py``.
"""
# Progressive families: remake actors in upgrade order. Every copy gives the level
# above the one Link holds (``patching.progressive``).
PROGRESSIVE = {
    'Progressive Hookshot': ['Item_Hookshot', 'Item_Longshot'],
    'Progressive Strength Upgrade': ['Item_Gauntlet_Goron', 'Item_Gauntlet_Silver', 'Item_Gauntlet_Gold'],
    'Bomb Bag': ['Item_BombBag_Small', 'Item_BombBag_Medium', 'Item_BombBag_Large'],
    'Bow': ['Item_Range_Bow', 'Item_Quiver_Medium', 'Item_Quiver_Large'],
    'Slingshot': ['Item_Range_SlingShot', 'Item_BulletBag_Medium', 'Item_BulletBag_Large'],
    'Progressive Scale': ['Item_Scale_Silver', 'Item_Scale_Gold'],
    'Progressive Wallet': ['Item_Wallet_Medium', 'Item_Wallet_Large'],
    'Deku Stick Capacity': ['Item_StickBag_Medium', 'Item_StickBag_Large'],
    'Deku Nut Capacity': ['Item_NutBag_Medium', 'Item_NutBag_Large'],
    'Magic Meter': ['Item_FairyBless_MP', 'Item_FairyBless_MPDouble'],
    'Ocarina': ['Item_Ocarina_Fairy', 'Item_Ocarina_Time'],
}
TOKEN_PREFIX = 'Item_Prog_'
APPLIED_PREFIX = 'RandoProg.'
# Family -> (actor code, English name, French name, actor lending its model).
FAMILIES = {
    'Progressive Hookshot': ('Hookshot', 'Hookshot', 'Grappin', 'Item_Hookshot'),
    'Progressive Strength Upgrade': ('Strength', 'Strength', 'Force', 'Item_Gauntlet_Goron'),
    'Bomb Bag': ('BombBag', 'Bomb Bag', 'Sac de bombes', 'Item_BombBag_Small'),
    'Bow': ('Bow', 'Bow', 'Arc', 'Weapon_Range_Bow'),
    'Slingshot': ('Slingshot', 'Slingshot', 'Lance-pierre', 'Weapon_Range_SlingShot'),
    'Progressive Scale': ('Scale', 'Scale', 'Écaille', 'Item_Scale_Silver'),
    'Progressive Wallet': ('Wallet', 'Wallet', 'Bourse', 'Item_Wallet_Medium'),
    'Deku Stick Capacity': ('Sticks', 'Deku Sticks', 'Bâtons Mojo', 'Item_StickBag_Medium'),
    'Deku Nut Capacity': ('Nuts', 'Deku Nuts', 'Noix Mojo', 'Item_NutBag_Medium'),
    'Magic Meter': ('Magic', 'Magic', 'Magie', 'Item_FairyBless_MP'),
    'Ocarina': ('Ocarina', 'Ocarina', 'Ocarina', 'Item_Ocarina_Fairy'),
}
FAMILY_OF_CODE = {code: family for family, (code, _, _, _) in FAMILIES.items()}


def token_actor(family, number):
    return f'{TOKEN_PREFIX}{FAMILIES[family][0]}_{number}'


def token_family(actor):
    """Family of a token actor, or None."""
    if not actor.startswith(TOKEN_PREFIX):
        return None
    code, _, number = actor[len(TOKEN_PREFIX):].rpartition('_')
    return FAMILY_OF_CODE.get(code) if number.isdigit() else None


def is_token(actor):
    return token_family(actor) is not None


def applied_flag(token):
    return APPLIED_PREFIX + token


def got_flag(token):
    return 'IsGet.' + token
