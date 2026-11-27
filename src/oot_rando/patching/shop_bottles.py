"""Full bottles on a shop shelf are bought like any other item, not as bottle contents.

``DisplayShop`` sorts the selected item (``EventQueryCheckShopSelectItemName``) and
sends category 5, bottle contents (fish, potions...), through two branches:

* ``SelectItem_CheckAvailable`` (Event318): ``EventQueryIsAnyBottleEmpty``, and with
  no empty bottle ``NotAvailableTalk`` ("<item>? Ah, darn...");
* the purchase (Event27): pay, then pour the contents into an empty bottle
  (Event47).

``Shop_SelectItemName`` is the shelf's pouch actor. Ruto's Letter, the Bottle with
Milk or an empty bottle placed on a shelf is a new bottle, yet the shop puts it in
category 5 and asked for an empty one (Discord 19/11, Ruto's Letter in the Kokiri
shop). For those actors only, both switches now take the branch of a plain item
(Event310, Event77). No shop of the remake sells them natively, so native bottle
contents keep their branch. Validated in game 19/11 (Ruto's Letter bought in the
Kokiri shop with no empty bottle).
"""
from oot_rando.patching.story_fixes import _Chart
from oot_rando.formats.evfl_tools import case_target

DISPLAY_SHOP_FLOW = 'Event/EventFlow/DisplayShop.bfevfl.zs'
# Pouch actors of the full bottles the randomizer can put on a shelf.
FULL_BOTTLES = ('Item_Bottle', 'Item_Bottle_Letter', 'Item_Bottle_Milk')
BOTTLE_CATEGORY = 5
SELECTED = 'Shop_SelectItemName'
# switch event -> (event of a plain item, event of bottle contents)
BRANCHES = {'Event318': ('Event310', 'Event325'), 'Event27': ('Event77', 'Event47')}
PREFIX = 'RandoFullBottle_'


def patch_display_shop(raw):
    """Return ``(bytes, report)``: the edited ``DisplayShop`` flow."""
    from evfl.util import make_index
    flow = _Chart(raw)
    report = {}
    for name, (plain_name, contents_name) in BRANCHES.items():
        switch = flow.event(name, 'SwitchEvent')
        if switch.data.actor_query.v.v != 'EventQueryCheckShopSelectItemName':
            raise ValueError('Unexpected shop item switch: ' + name)
        contents, plain = case_target(switch, BOTTLE_CATEGORY), flow.events.get(plain_name)
        if contents is None or contents.name != contents_name or plain is None:
            raise ValueError('Unexpected bottle branch in the shop flow: ' + name)
        if not any(case_target(switch, key) is plain for key in switch.data.cases if key != BOTTLE_CATEGORY):
            raise ValueError('Plain item branch not found in the shop flow: ' + name)
        following = contents
        for actor in reversed(FULL_BOTTLES):
            following = flow.switch(f'{PREFIX}{name}_{actor}', 'EventQueryIsGameDataString64',
                                    {'GameDataName': SELECTED, 'Index': -1, 'Value': actor}, plain, following)
        switch.data.cases[BOTTLE_CATEGORY] = make_index(following)
        report[name] = {'plain': plain_name, 'contents': contents_name, 'guard': following.name}
    result, events = flow.write()
    for name, (plain_name, contents_name) in BRANCHES.items():
        guard = case_target(events[name], BOTTLE_CATEGORY)
        for actor in FULL_BOTTLES:
            if (guard is None or guard.data.params.data.get('Value') != actor
                    or case_target(guard, 0) is None or case_target(guard, 0).name != plain_name):
                raise ValueError('Full bottle guard not written: ' + name)
            guard = case_target(guard, 1)
        if guard is None or guard.name != contents_name:
            raise ValueError('Bottle contents branch lost: ' + name)
    return result, report
