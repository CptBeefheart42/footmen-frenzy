// FF e2e test addon — core (tests/e2e; built into bin/e2e/*.w3x only, never a release: verify-map rejects
// FF_E2E_ symbols). A scenario file defines FF_E2E_Scenario and FF_E2E_HostClick; the build calls FF_E2E_Init
// (99-e2e-init.j) from main(), which starts the scenario.
// The helpers here are shared by every scenario: records, the runner hand-shake, kills, purchases and the end of a
// game.
//
// Two files in CustomMapData, Preload format, both local to the one test client:
//   ff_e2e.txt        the scenario's records (`<kind>,<key>=<value>,...`), `END` as the last record once done
//   ff_e2e_phase.txt  `WAIT <n> chat <text>`: asks tests/e2e/run.py to type <text> into the chat; the
//                     scenario's chat trigger sees it and moves on (FF_E2E_WaitChat)
//                     `WAIT 0 click <x> <y>`: at map init, when the client is the host (Player 0): click the host's
//                     game-type dialog at (x, y) relative to the window — a dialog pauses a single-player game, so
//                     nothing runs until it is answered; `OK 0` once the scenario starts (the dialog is gone)
//                     `WAIT <n> key <key>`: press <key> once (a shop's command-card hotkey, the shop selected)

globals
    string array FF_E2E_rows
    integer FF_E2E_n = 0
    integer FF_E2E_phase = 0
    string FF_E2E_waitText = null
    trigger FF_E2E_chatTrig = null
    code FF_E2E_next = null
    string FF_E2E_clickAfter = null
    // FF_E2E_BuyByKey
    unit FF_E2E_buyer = null
    integer FF_E2E_soldItem = 0
    trigger FF_E2E_sellTrig = null
    code FF_E2E_buyNext = null
    // FF_E2E_Raze
    trigger FF_E2E_razeTrig = null
    integer FF_E2E_razeCasts = 0
    integer FF_E2E_razeDirect = 0
    unit FF_E2E_razeCaster = null
    unit FF_E2E_razeTarget = null
    // FF_E2E_EndGame
    integer array FF_E2E_bases
    integer FF_E2E_baseCount = 0
    integer FF_E2E_basePos = 0
    boolean FF_E2E_baseByRaze = false
    integer FF_E2E_endWaited = 0
    code FF_E2E_endNext = null
endglobals

// --- small helpers ---------------------------------------------------------------------------------------------

// Runs `next` after `secs` game seconds (one-shot timer; the scenarios are chains of these).
function FF_E2E_After takes real secs, code next returns nothing
    call TimerStart(CreateTimer(), secs, false, next)
endfunction

// Game seconds since the addons booted (FF_gameTimer starts at 0.1s).
function FF_E2E_Now takes nothing returns integer
    return R2I(TimerGetElapsed(FF_gameTimer))
endfunction

function FF_E2E_R2S takes real r returns string
    return I2S(R2I(r))
endfunction

function FF_E2E_Bool takes boolean b returns string
    if b then
        return "1"
    endif
    return "0"
endfunction

function FF_E2E_Ctrl takes player p returns string
    local mapcontrol c = GetPlayerController(p)
    if c == MAP_CONTROL_USER then
        return "user"
    elseif c == MAP_CONTROL_COMPUTER then
        return "computer"
    elseif c == MAP_CONTROL_NEUTRAL then
        return "neutral"
    endif
    return "other"
endfunction

function FF_E2E_State takes player p returns string
    local playerslotstate st = GetPlayerSlotState(p)
    if st == PLAYER_SLOT_STATE_PLAYING then
        return "playing"
    elseif st == PLAYER_SLOT_STATE_LEFT then
        return "left"
    endif
    return "empty"
endfunction

// --- records and the runner hand-shake -------------------------------------------------------------------------

// Rewrites ff_e2e.txt with every record so far (the file is always complete, even if the game stops).
function FF_E2E_Flush takes nothing returns nothing
    local integer i = 0
    call PreloadGenClear()
    call PreloadGenStart()
    loop
        exitwhen i >= FF_E2E_n
        call Preload(FF_E2E_rows[i])
        set i = i + 1
    endloop
    call PreloadGenEnd("ff_e2e.txt")
endfunction

function FF_E2E_Row takes string row returns nothing
    set FF_E2E_rows[FF_E2E_n] = row
    set FF_E2E_n = FF_E2E_n + 1
    call FF_E2E_Flush()
endfunction

// The scenario is finished: the runner stops the game once it reads `END`.
function FF_E2E_Done takes nothing returns nothing
    call FF_E2E_Row("END")
endfunction

function FF_E2E_PhaseFile takes string row returns nothing
    call PreloadGenClear()
    call PreloadGenStart()
    call Preload(row)
    call PreloadGenEnd("ff_e2e_phase.txt")
endfunction

// Asks the runner to type `text` in the chat; `next` runs once the map has seen it.
function FF_E2E_WaitChat takes string text, code next returns nothing
    set FF_E2E_phase = FF_E2E_phase + 1
    set FF_E2E_waitText = text
    set FF_E2E_next = next
    call FF_E2E_PhaseFile("WAIT " + I2S(FF_E2E_phase) + " chat " + text)
endfunction

// Like FF_E2E_WaitChat, for a command that opens a dialog (which pauses a single-player game): as soon as the map
// sees the command, the runner is asked to click `click` ("<x> <y>", relative to the window). `next` runs once the
// game goes on and should say so with FF_E2E_Ok (the runner clicks again until then).
function FF_E2E_WaitChatClick takes string text, string click, code next returns nothing
    call FF_E2E_WaitChat(text, next)
    set FF_E2E_clickAfter = click
endfunction

// Asks the runner to press `key` once (no acknowledgement: the scenario checks the effect itself).
function FF_E2E_Key takes string key returns nothing
    set FF_E2E_phase = FF_E2E_phase + 1
    call FF_E2E_PhaseFile("WAIT " + I2S(FF_E2E_phase) + " key " + key)
endfunction

function FF_E2E_Ok takes nothing returns nothing
    call FF_E2E_PhaseFile("OK " + I2S(FF_E2E_phase))
endfunction

// The chat trigger: the text the runner was asked to type has arrived, so the scenario moves on.
function FF_E2E_OnChat takes nothing returns nothing
    if FF_E2E_waitText != null and GetEventPlayerChatString() == FF_E2E_waitText then
        set FF_E2E_waitText = null
        call FF_E2E_Row("chat,phase=" + I2S(FF_E2E_phase) + ",slot=" + I2S(GetPlayerId(GetTriggerPlayer()) + 1) + ",text=" + GetEventPlayerChatString())
        if FF_E2E_clickAfter != null then
            set FF_E2E_phase = FF_E2E_phase + 1
            call FF_E2E_PhaseFile("WAIT " + I2S(FF_E2E_phase) + " click " + FF_E2E_clickAfter)
            set FF_E2E_clickAfter = null
        endif
        call FF_E2E_After(1.0, FF_E2E_next)
    endif
endfunction

// The scenario's first records: its name, who the client is, the game token and result file name, and every slot
// in use (controller, state, team, name).
function FF_E2E_Begin takes string scenario returns nothing
    local integer i = 0
    local player p
    call FF_E2E_Row("e2e,scenario=" + scenario + ",local=" + I2S(GetPlayerId(GetLocalPlayer())) + ",bot=" + FF_E2E_Bool(FF_LocalClientIsBot()) + ",token=" + FF_gameToken + ",file=" + FF_DataFile("ff_result"))
    loop
        exitwhen i >= bj_MAX_PLAYER_SLOTS
        set p = Player(i)
        if GetPlayerSlotState(p) != PLAYER_SLOT_STATE_EMPTY then
            call FF_E2E_Row("slot," + I2S(i) + ",ctrl=" + FF_E2E_Ctrl(p) + ",state=" + FF_E2E_State(p) + ",team=" + I2S(GetPlayerTeam(p)) + ",name=" + GetPlayerName(p))
        endif
        set i = i + 1
    endloop
    set p = null
endfunction

// --- units -----------------------------------------------------------------------------------------------------

// `killer` deals `victim` far more damage than it has: a real kill the map's own death triggers count.
function FF_E2E_Kill takes unit killer, unit victim returns nothing
    call UnitDamageTarget(killer, victim, 100000.0, true, false, ATTACK_TYPE_CHAOS, DAMAGE_TYPE_UNIVERSAL, WEAPON_TYPE_WHOKNOWS)
endfunction

// The living unit of a type owned by p nearest to (x, y), or null.
function FF_E2E_Nearest takes player p, integer typeId, real x, real y returns unit
    local group g = CreateGroup()
    local unit u
    local unit best = null
    local real bd = 1000000000.0
    local real d
    call GroupEnumUnitsOfPlayer(g, p, null)
    loop
        set u = FirstOfGroup(g)
        exitwhen u == null
        call GroupRemoveUnit(g, u)
        if GetUnitTypeId(u) == typeId and FF_UnitAlive(u) then
            set d = (GetUnitX(u) - x) * (GetUnitX(u) - x) + (GetUnitY(u) - y) * (GetUnitY(u) - y)
            if d < bd then
                set bd = d
                set best = u
            endif
        endif
    endloop
    call DestroyGroup(g)
    set g = null
    return best
endfunction

// --- purchases -------------------------------------------------------------------------------------------------

// Orders `shop` to sell slot 1 the first item of the weapons shop's list it has in stock (some only come into stock
// later) and records the outcome (`item,order=1,id=..` or `item,order=0`). Returns the item type, 0 if none sold.
// The buyer is vulnerable during the order: the weapons shop ignores an invulnerable buyer.
function FF_E2E_BuyFirstItem takes unit buyer, unit shop returns integer
    local integer array ids
    local integer i = 0
    set ids[0] = 'ratf'
    set ids[1] = 'ofro'
    set ids[2] = 'oven'
    set ids[3] = 'olig'
    set ids[4] = 'I03C'
    set ids[5] = 'I02J'
    set ids[6] = 'sbch'
    set ids[7] = 'tmmt'
    set ids[8] = 'ward'
    call SetUnitInvulnerable(buyer, false)
    loop
        exitwhen i > 8
        if IssueNeutralImmediateOrderById(Player(0), shop, ids[i]) then
            call FF_E2E_Row("item,order=1,id=" + FF_us_Id2S(ids[i]) + ",tried=" + I2S(i + 1) + ",t=" + I2S(FF_E2E_Now()))
            call SetUnitInvulnerable(buyer, true)
            return ids[i]
        endif
        set i = i + 1
    endloop
    call SetUnitInvulnerable(buyer, true)
    call FF_E2E_Row("item,order=0,tried=9,t=" + I2S(FF_E2E_Now()))
    return 0
endfunction

function FF_E2E_OnSellItem takes nothing returns nothing
    if GetBuyingUnit() == FF_E2E_buyer and FF_E2E_soldItem == 0 then
        set FF_E2E_soldItem = GetItemTypeId(GetSoldItem())
    endif
endfunction

function FF_E2E_BuyPress takes nothing returns nothing
    call FF_E2E_Key("q")
    call FF_E2E_After(4.0, FF_E2E_buyNext)
endfunction

// Buys the first item of `shop`'s command card the way a player does: `buyer` next to the shop, the shop selected
// for the client, the runner presses its hotkey (Q). The engine refuses IssueNeutralImmediateOrderById for the main
// map's weapons shop although it sells to players. FF_E2E_soldItem = what was sold, 0 if nothing; `next` runs ~5s
// later (the buyer stays vulnerable and the shop selected until then).
function FF_E2E_BuyByKey takes unit buyer, unit shop, code next returns nothing
    set FF_E2E_buyer = buyer
    set FF_E2E_soldItem = 0
    set FF_E2E_buyNext = next
    if FF_E2E_sellTrig == null then
        set FF_E2E_sellTrig = CreateTrigger()
        call TriggerRegisterAnyUnitEventBJ(FF_E2E_sellTrig, EVENT_PLAYER_UNIT_SELL_ITEM)
        call TriggerAddAction(FF_E2E_sellTrig, function FF_E2E_OnSellItem)
    endif
    call SetUnitPosition(buyer, GetUnitX(shop) + 150.0, GetUnitY(shop))
    call SetUnitInvulnerable(buyer, false)
    if UnitInventoryCount(buyer) >= UnitInventorySize(buyer) then
        call RemoveItem(UnitItemInSlot(buyer, UnitInventorySize(buyer) - 1))
    endif
    if GetLocalPlayer() == GetOwningPlayer(buyer) then
        call ClearSelection()
        call SelectUnit(shop, true)
    endif
    call FF_E2E_After(1.0, function FF_E2E_BuyPress)
endfunction

// --- Raze: a kill through a real cast --------------------------------------------------------------------------

function FF_E2E_OnRaze takes nothing returns nothing
    if GetSpellAbilityId() == 'E2Ra' and GetSpellTargetUnit() != null then
        set FF_E2E_razeCasts = FF_E2E_razeCasts + 1
        call UnitDamageTarget(GetTriggerUnit(), GetSpellTargetUnit(), 1000000.0, true, false, ATTACK_TYPE_CHAOS, DAMAGE_TYPE_UNIVERSAL, WEAPON_TYPE_WHOKNOWS)
    endif
endfunction

// Issues the Raze order; when the engine refuses it, records why and deals the damage directly.
function FF_E2E_RazeOrder takes nothing returns nothing
    local unit caster = FF_E2E_razeCaster
    local unit target = FF_E2E_razeTarget
    local boolean ok
    local string how = "creepthunderbolt"
    local unit probe
    local boolean probeOk
    call DestroyTimer(GetExpiredTimer())
    set ok = IssueTargetOrder(caster, "creepthunderbolt", target)
    if not ok then
        // refused from afar: next to the target, like a player who walked there
        set how = "near"
        call SetUnitPosition(caster, GetUnitX(target) - 300.0, GetUnitY(target))
        set ok = IssueTargetOrder(caster, "creepthunderbolt", target)
    endif
    if ok then
        call FF_E2E_Row("raze,target=" + FF_us_Id2S(GetUnitTypeId(target)) + ",order=1,how=" + how)
    else
        // the same order on an enemy footman next to the caster tells a target-list / visibility problem apart
        // from the ability itself
        set probe = CreateUnit(Player(3), 'hfoo', GetUnitX(caster) + 150.0, GetUnitY(caster), 0.0)
        set probeOk = IssueTargetOrder(caster, "creepthunderbolt", probe)
        call IssueImmediateOrder(caster, "stop")
        call RemoveUnit(probe)
        call FF_E2E_Row("raze,target=" + FF_us_Id2S(GetUnitTypeId(target)) + ",order=0,abil=" + I2S(GetUnitAbilityLevel(caster, 'E2Ra')) + ",visible=" + FF_E2E_Bool(IsUnitVisible(target, GetOwningPlayer(caster))) + ",probe=" + FF_E2E_Bool(probeOk) + ",dist=" + FF_E2E_R2S(SquareRoot((GetUnitX(caster) - GetUnitX(target)) * (GetUnitX(caster) - GetUnitX(target)) + (GetUnitY(caster) - GetUnitY(target)) * (GetUnitY(caster) - GetUnitY(target)))))
        set FF_E2E_razeDirect = FF_E2E_razeDirect + 1
        call UnitDamageTarget(caster, target, 1000000.0, true, false, ATTACK_TYPE_CHAOS, DAMAGE_TYPE_UNIVERSAL, WEAPON_TYPE_WHOKNOWS)
    endif
    set caster = null
    set target = null
    set probe = null
endfunction

// Kills `target` the way a player would: `caster` (a hero) casts the e2e build's own ability E2Ra ("Raze", a creep
// Storm Bolt copy with unlimited range, no cost, no cooldown: scripting/jass-e2e/core/object_overrides.csv) on it,
// and the spell's effect deals the killing damage from the caster. The target's vision is shared with the caster's
// owner first and the order follows 0.5s later (the engine refuses an order on a unit its owner can't see). If the
// order is refused the damage is dealt directly, and the record says so and why (`raze,...,order=0,...`): the checks
// want every kill to have been a cast. One raze at a time (the scenarios space them by seconds).
function FF_E2E_Raze takes unit caster, unit target returns nothing
    if FF_E2E_razeTrig == null then
        set FF_E2E_razeTrig = CreateTrigger()
        call TriggerRegisterAnyUnitEventBJ(FF_E2E_razeTrig, EVENT_PLAYER_UNIT_SPELL_EFFECT)
        call TriggerAddAction(FF_E2E_razeTrig, function FF_E2E_OnRaze)
    endif
    if GetUnitAbilityLevel(caster, 'E2Ra') == 0 then
        call UnitAddAbility(caster, 'E2Ra')
    endif
    call UnitShareVision(target, GetOwningPlayer(caster), true)
    set FF_E2E_razeCaster = caster
    set FF_E2E_razeTarget = target
    call FF_E2E_After(0.5, function FF_E2E_RazeOrder)
endfunction

// --- the end of a game: bases fall until one side is left ------------------------------------------------------

// Adds a slot to the bases FF_E2E_EndGame destroys, in the order they are added.
function FF_E2E_AddBase takes integer slot returns nothing
    set FF_E2E_bases[FF_E2E_baseCount] = slot
    set FF_E2E_baseCount = FF_E2E_baseCount + 1
endfunction

// Waits for the result addon's gameend (it checks every second); the map's END hands out victory / defeat ~20s
// after the last base. Gives up after 30s (`ended,timeout=30`, then END).
function FF_E2E_EndWait takes nothing returns nothing
    if FF_gr_ended then
        if FF_E2E_baseByRaze then
            call FF_E2E_Row("razes,casts=" + I2S(FF_E2E_razeCasts) + ",direct=" + I2S(FF_E2E_razeDirect))
        endif
        call FF_E2E_Row("ended,t=" + I2S(FF_E2E_Now()) + ",active=" + FF_E2E_Bool(udg_player_active[1]) + FF_E2E_Bool(udg_player_active[2]) + FF_E2E_Bool(udg_player_active[3]))
        call FF_E2E_After(3.0, FF_E2E_endNext)
        return
    endif
    set FF_E2E_endWaited = FF_E2E_endWaited + 1
    if FF_E2E_endWaited > 30 then
        call FF_E2E_Row("ended,timeout=30")
        call FF_E2E_Done()
        return
    endif
    call FF_E2E_After(1.0, function FF_E2E_EndWait)
endfunction

// Destroys the next base on the list (every 3s), recording the slot's gold right before: the map hands it to the
// slot's surviving allies.
function FF_E2E_EndNextBase takes nothing returns nothing
    local integer s = FF_E2E_bases[FF_E2E_basePos]
    local unit b = udg_base[s]
    call FF_E2E_Row("razebase,slot=" + I2S(s) + ",gold=" + I2S(GetPlayerState(Player(s - 1), PLAYER_STATE_RESOURCE_GOLD)) + ",type=" + FF_us_Id2S(GetUnitTypeId(b)) + ",hp=" + FF_E2E_R2S(GetUnitState(b, UNIT_STATE_MAX_LIFE)) + ",alive=" + FF_E2E_Bool(FF_UnitAlive(b)) + ",t=" + I2S(FF_E2E_Now()))
    if FF_E2E_baseByRaze then
        call FF_E2E_Raze(udg_herO[1], b)
    else
        call FF_E2E_Kill(udg_herO[1], b)
    endif
    set b = null
    set FF_E2E_basePos = FF_E2E_basePos + 1
    if FF_E2E_basePos >= FF_E2E_baseCount then
        set FF_E2E_endWaited = 0
        call FF_E2E_After(1.0, function FF_E2E_EndWait)
        return
    endif
    call FF_E2E_After(3.0, function FF_E2E_EndNextBase)
endfunction

// Plays the game to its end: slot 1's hero destroys the bases added with FF_E2E_AddBase, one every 3s, by a direct
// kill or (`byRaze`) through the Raze cast. Once the result addon has written gameend, `next` runs 3s later (the
// final flush); it must end with FF_E2E_Done.
function FF_E2E_EndGame takes boolean byRaze, code next returns nothing
    set FF_E2E_baseByRaze = byRaze
    set FF_E2E_endNext = next
    set FF_E2E_basePos = 0
    call FF_E2E_After(1.0, function FF_E2E_EndNextBase)
endfunction
