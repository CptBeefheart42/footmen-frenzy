-- Exercise Info on the second active participant's client. The simulation's normal UI natives
-- do nothing, so retain just frame identity, parent and visibility for these assertions.
local playerSlot = T.map == "799x" and 2 or 5
T.lobby(T.defaultLobby(), playerSlot)
local visible, parent, events = {}, {}, {}
function BlzCreateFrame() return {} end
function BlzCreateFrameByType() return {} end
function BlzFrameSetVisible(frame, shown) if frame then visible[frame] = shown end end
function BlzFrameSetParent(frame, target) parent[frame] = target end
function BlzTriggerRegisterFrameEvent(trigger, frame, event)
    if frame and event == FRAMEEVENT_CONTROL_CLICK then events[frame] = trigger end
end
T.boot()
T.advance(20)
local viewer = Player(playerSlot - 1)
local clicked, eventPlayer = DPS_Button, viewer
function GetTriggerPlayer() return eventPlayer end
function BlzGetTriggerFrame() return clicked end
T.check("Info opens match stats and contains a working Hotkeys button", function()
    T.ok(DPS_Ready and DPS_Panel ~= nil, "stats ready")
    T.ok(spellKeysToggle ~= nil and events[spellKeysToggle] ~= nil, "hotkey click registered")
    T.eq(parent[spellKeysToggle], DPS_Panel, "Hotkeys belongs to Info")
    DPS_Toggle()
    T.eq(visible[DPS_Panel], true, "open stats")
    clicked = spellKeysToggle
    SpellKeysClick()
    T.eq(visible[spellKeysPanel], true, "editor opens")
    clicked = spellKeysRows[1]
    SpellKeysClick()
    function BlzGetTriggerPlayerKey() return { __id = 71 } end
    function BlzGetTriggerPlayerMetaKey() return 0 end
    SpellKeysInput()
    T.eq(spellKeysBinding[1], 71, "spell key assigned")
    clicked = spellKeysClose
    SpellKeysClick()
    T.eq(visible[spellKeysPanel], false, "editor closes")
    T.eq(visible[DPS_Panel], true, "back to match stats")
    eventPlayer = Player(0)
    DPS_Toggle()
    T.eq(visible[DPS_Panel], true, "another player leaves this view alone")
end)
