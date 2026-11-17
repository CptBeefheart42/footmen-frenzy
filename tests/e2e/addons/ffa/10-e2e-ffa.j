// e2e scenario "ffa": one short main-map game played to its end by script, with the client as player 1 (slot 1,
// a participant; slots 2-12 are computers — `slots` file). The host (the client) stays AFK, so the map starts its
// default game itself: Pub, SD, King of the Hill on. Everything below happens through real orders, real damage
// and the map's own triggers; tests/e2e/check_e2e.py judges ff_result / ff_killlog against these records.
//   t~3     heroes for every slot (created in the tavern area: the map's TP_hero makes them the slots' heroes —
//           the computers never pick one, the map has no AI); slot 1 gets the Alchemist (N01C, Transmute)
//   then    slot 1 buys an item (weapons shop) and a creep (its team's creep shop), researches attack x2 + armor
//           at its base and creep armor at its team's upgrade shop, upgrades a tower, learns Transmute
//   chat    -kd, -time, -cam, -zoom 3500 typed by tests/e2e/run.py (player chat: counted as `use,1,cmd`)
//   then    kills by slot 1's hero: an own footman (deny_own), an ally's (deny_ally), an enemy footman and an enemy
//           hero; Transmute three times: a hit, one the target's owner kills first (denied / tm_saves), one dodged
//   t>=250  base upgrade to tier 1 (h00W, after the map's tech delay); -pool, the runner clicks the dialog's first
//           ally button (slot 2): the map's own autopool moves the gold; King of the Hill: slot 1's hero takes the
//           hill and holds it
//   end     slot 4 gets 1000 gold, then the bases of slots 4..12 fall one by one (team 2 first, so slot 4's gold
//           is inherited by slots 5 and 6); team 1 wins, the map's END runs, ff_result gets gameend

globals
    unit FF_E2E_hero = null
    unit FF_E2E_tmTarget = null
    unit FF_E2E_tmKiller = null
    integer FF_E2E_tmMode = 0
    integer FF_E2E_waited = 0
    integer FF_E2E_uk0 = 0
    integer FF_E2E_hk0 = 0
    integer FF_E2E_gold2 = 0
    integer FF_E2E_item = 0
    integer FF_E2E_tmTries = 0
    code FF_E2E_tmCastCode = null
endglobals

function FF_E2E_CountOf takes player p, integer typeId returns integer
    local group g = CreateGroup()
    local unit u
    local integer n = 0
    call GroupEnumUnitsOfPlayer(g, p, null)
    loop
        set u = FirstOfGroup(g)
        exitwhen u == null
        call GroupRemoveUnit(g, u)
        if GetUnitTypeId(u) == typeId and FF_UnitAlive(u) then
            set n = n + 1
        endif
    endloop
    call DestroyGroup(g)
    set g = null
    return n
endfunction

function FF_E2E_Gold takes integer slot returns integer
    return GetPlayerState(Player(slot - 1), PLAYER_STATE_RESOURCE_GOLD)
endfunction

// Why the weapons shop refuses: its select/sell abilities, and a plain footman of slot 1 as the buyer at both shops.
function FF_E2E_FfaShopDiag takes nothing returns nothing
    local unit shop = gg_unit_n01B_0055
    local unit foot = CreateUnit(Player(0), 'hfoo', GetUnitX(shop) + 120.0, GetUnitY(shop), 0.0)
    local string a = "shopdiag,Aneu=" + I2S(GetUnitAbilityLevel(shop, 'Aneu')) + ",Ane2=" + I2S(GetUnitAbilityLevel(shop, 'Ane2')) + ",Apit=" + I2S(GetUnitAbilityLevel(shop, 'Apit')) + ",Asid=" + I2S(GetUnitAbilityLevel(shop, 'Asid')) + ",Aall=" + I2S(GetUnitAbilityLevel(shop, 'Aall')) + ",A021=" + I2S(GetUnitAbilityLevel(shop, 'A021')) + ",A022=" + I2S(GetUnitAbilityLevel(shop, 'A022')) + ",A05R=" + I2S(GetUnitAbilityLevel(shop, 'A05R')) + ",owner=" + I2S(GetPlayerId(GetOwningPlayer(shop)))
    set a = a + ",foot=" + FF_E2E_Bool(IssueNeutralImmediateOrderById(Player(0), shop, 'ratf'))
    call SetUnitPosition(FF_E2E_hero, GetUnitX(gg_unit_n01B_0056) - 150.0, GetUnitY(gg_unit_n01B_0056))
    call SetUnitInvulnerable(FF_E2E_hero, false)
    set a = a + ",shop2=" + FF_E2E_Bool(IssueNeutralImmediateOrderById(Player(0), gg_unit_n01B_0056, 'ratf')) + ",byName=" + FF_E2E_Bool(IssueNeutralImmediateOrder(Player(0), gg_unit_n01B_0056, "ratf"))
    call SetUnitInvulnerable(FF_E2E_hero, true)
    call FF_E2E_Row(a)
    call RemoveUnit(foot)
    set shop = null
    set foot = null
endfunction

// The scripted purchase (the engine refuses it at the weapons shop) and the shop's abilities, for the record.
function FF_E2E_FfaBuyItem takes nothing returns nothing
    set FF_E2E_item = FF_E2E_BuyFirstItem(FF_E2E_hero, gg_unit_n01B_0055)
    if FF_E2E_item == 0 then
        call FF_E2E_FfaShopDiag()
    endif
endfunction

// --- the end: bases of slots 4..12 fall, team 2 first ----------------------------------------------------------

function FF_E2E_FfaFinish takes nothing returns nothing
    call FF_E2E_Done()
endfunction

// Slot 4 gets 1000 gold to hand on, then the bases of slots 4..12 fall, team 2 first.
function FF_E2E_FfaEndgame takes nothing returns nothing
    local integer s = 4
    call SetPlayerState(Player(3), PLAYER_STATE_RESOURCE_GOLD, 1000)
    loop
        exitwhen s > 12
        call FF_E2E_AddBase(s)
        set s = s + 1
    endloop
    call FF_E2E_EndGame(false, function FF_E2E_FfaFinish)
endfunction

// --- King of the Hill ------------------------------------------------------------------------------------------

function FF_E2E_FfaKothRead takes nothing returns nothing
    call FF_E2E_Row("koth,holder=" + I2S(GetPlayerId(udg_KOTH_Player) + 1) + ",gold1=" + I2S(FF_st_kothGold[1]) + ",gold2=" + I2S(FF_st_kothGold[2]) + ",gold3=" + I2S(FF_st_kothGold[3]) + ",t=" + I2S(FF_E2E_Now()))
    call FF_E2E_FfaEndgame()
endfunction

function FF_E2E_FfaKothTake takes nothing returns nothing
    if udg_KOTH_Hill == null or not FF_UnitAlive(udg_KOTH_Hill) then
        set FF_E2E_waited = FF_E2E_waited + 2
        if FF_E2E_waited > 240 then
            call FF_E2E_Row("koth,timeout=240")
            call FF_E2E_FfaEndgame()
            return
        endif
        call FF_E2E_After(2.0, function FF_E2E_FfaKothTake)
        return
    endif
    call FF_E2E_Row("koth,take=1,t=" + I2S(FF_E2E_Now()))
    call SetUnitPosition(FF_E2E_hero, GetUnitX(udg_KOTH_Hill) + 150.0, GetUnitY(udg_KOTH_Hill))
    call FF_E2E_Kill(FF_E2E_hero, udg_KOTH_Hill)
    call FF_E2E_After(30.0, function FF_E2E_FfaKothRead)
endfunction

// --- base upgrade + autopool -----------------------------------------------------------------------------------

function FF_E2E_FfaPoolRead takes nothing returns nothing
    call FF_E2E_Row("pool,read=1,out1=" + I2S(FF_st_poolOut[1]) + ",in2=" + I2S(FF_st_poolIn[2]) + ",gold2_before=" + I2S(FF_E2E_gold2) + ",gold2_after=" + I2S(FF_E2E_Gold(2)) + ",gold1=" + I2S(FF_E2E_Gold(1)))
    set FF_E2E_waited = 0
    call FF_E2E_FfaKothTake()
endfunction

// After -pool and the runner's click on the dialog's first ally button (the game is paused until then): the map's
// own autopool sends slot 1's gold above its threshold to that ally every 2s, from now on.
function FF_E2E_FfaPool takes nothing returns nothing
    call FF_E2E_Ok()
    call FF_E2E_Row("pool,allowed=" + FF_E2E_Bool(udg_autopoool_allowed) + ",ally1=" + I2S(GetPlayerId(udg_ally1[1]) + 1) + ",to=" + I2S(udg_autopoolto[1]) + ",threshold=" + I2S(udg_pool_threshold[1]))
    set FF_E2E_gold2 = FF_E2E_Gold(2)
    call FF_E2E_After(5.0, function FF_E2E_FfaPoolRead)
endfunction

function FF_E2E_FfaBaseWait takes nothing returns nothing
    if GetUnitTypeId(udg_base[1]) == 'h00W' then
        call FF_E2E_Row("baseup,slot=1,type=h00W,t=" + I2S(FF_E2E_Now()))
        call FF_E2E_WaitChatClick("-pool", "0.5 0.479", function FF_E2E_FfaPool)
        return
    endif
    set FF_E2E_waited = FF_E2E_waited + 2
    if FF_E2E_waited > 300 then
        call FF_E2E_Row("baseup,timeout=300,type=" + FF_us_Id2S(GetUnitTypeId(udg_base[1])))
        call FF_E2E_WaitChatClick("-pool", "0.5 0.479", function FF_E2E_FfaPool)
        return
    endif
    // the order is refused until the map's tier-1 tech delay (R00D) is researched: repeat it
    call IssueImmediateOrderById(udg_base[1], 'h00W')
    call FF_E2E_After(2.0, function FF_E2E_FfaBaseWait)
endfunction

function FF_E2E_FfaMid takes nothing returns nothing
    if FF_E2E_Now() < 250 then
        call FF_E2E_After(2.0, function FF_E2E_FfaMid)
        return
    endif
    call SetPlayerState(Player(0), PLAYER_STATE_RESOURCE_GOLD, 20000)
    set FF_E2E_waited = 0
    call FF_E2E_FfaBaseWait()
endfunction

// --- Transmute: hit, denied, dodged ----------------------------------------------------------------------------

// Runs on our hero's Transmute (after the stats addon registered the cast: its trigger is older).
function FF_E2E_FfaOnSpell takes nothing returns nothing
    if GetTriggerUnit() != FF_E2E_hero or GetSpellAbilityId() != 'ANtm' then
        return
    endif
    if FF_E2E_tmMode == 2 then
        call FF_E2E_Kill(FF_E2E_tmKiller, FF_E2E_tmTarget)
    elseif FF_E2E_tmMode == 3 then
        // the target is gone before the missile lands (moving, hiding or invulnerability did not stop it — the
        // missile follows its target): no death at all, so the stats addon's 4s expiry counts it as dodged
        call RemoveUnit(FF_E2E_tmTarget)
    endif
endfunction

function FF_E2E_FfaTmDone takes nothing returns nothing
    call FF_E2E_Row("transmute,casts=" + I2S(FF_st_tmCasts[1]) + ",hits=" + I2S(FF_st_tmHits[1]) + ",denied=" + I2S(FF_st_tmDenied[1]) + ",saves4=" + I2S(FF_st_tmSaves[4]))
    call SetHeroLevel(FF_E2E_hero, 6, false)
    call FF_E2E_After(1.0, function FF_E2E_FfaMid)
endfunction

// The cast order, again every second while the hero refuses it (it can refuse a cast 6s after the previous one).
function FF_E2E_FfaTmOrder takes nothing returns nothing
    local boolean ok
    call UnitResetCooldown(FF_E2E_hero)
    call SetUnitState(FF_E2E_hero, UNIT_STATE_MANA, GetUnitState(FF_E2E_hero, UNIT_STATE_MAX_MANA))
    set ok = IssueTargetOrder(FF_E2E_hero, "transmute", FF_E2E_tmTarget)
    set FF_E2E_tmTries = FF_E2E_tmTries + 1
    if not ok and FF_E2E_tmTries < 10 then
        call FF_E2E_After(1.0, function FF_E2E_FfaTmOrder)
        return
    endif
    call FF_E2E_Row("transmute,cast=" + I2S(FF_E2E_tmMode) + ",order=" + FF_E2E_Bool(ok) + ",tries=" + I2S(FF_E2E_tmTries) + ",t=" + I2S(FF_E2E_Now()))
    // FF_E2E_FfaTmCast is defined below (it calls this): reached through a code global set by the scenario
    call FF_E2E_After(6.0, FF_E2E_tmCastCode)
endfunction

// At the map centre (empty before Mass START at ~98s; no towers in reach), so nothing else touches the targets.
function FF_E2E_FfaTmCast takes nothing returns nothing
    local real x = 0.0
    local real y = -256.0
    set FF_E2E_tmMode = FF_E2E_tmMode + 1
    if FF_E2E_tmMode > 3 then
        call FF_E2E_After(5.0, function FF_E2E_FfaTmDone)
        return
    endif
    call SetUnitPosition(FF_E2E_hero, x, y)
    set FF_E2E_tmTarget = CreateUnit(Player(3), 'hfoo', x + 300.0, y, 180.0)
    set FF_E2E_tmKiller = CreateUnit(Player(3), 'hfoo', x + 400.0, y, 180.0)
    call PauseUnit(FF_E2E_tmTarget, true)
    call PauseUnit(FF_E2E_tmKiller, true)
    set FF_E2E_tmTries = 0
    call FF_E2E_FfaTmOrder()
endfunction

// --- kills and denies by slot 1's hero -------------------------------------------------------------------------

function FF_E2E_FfaKillsRead takes nothing returns nothing
    call FF_E2E_Row("kills,slot=1,ukills0=" + I2S(FF_E2E_uk0) + ",ukills1=" + I2S(udg_unit_kills[1]) + ",hkills0=" + I2S(FF_E2E_hk0) + ",hkills1=" + I2S(udg_hero_kills[1]) + ",deny_own=" + I2S(FF_st_denyOwn[1]) + ",deny_ally=" + I2S(FF_st_denyAlly[1]))
    set FF_E2E_tmMode = 0
    call FF_E2E_FfaTmCast()
endfunction

function FF_E2E_FfaKills takes nothing returns nothing
    local real x = GetUnitX(FF_E2E_hero)
    local real y = GetUnitY(FF_E2E_hero)
    set FF_E2E_uk0 = udg_unit_kills[1]
    set FF_E2E_hk0 = udg_hero_kills[1]
    call FF_E2E_Row("denies,before_own=" + I2S(FF_st_denyOwn[1]) + ",before_ally=" + I2S(FF_st_denyAlly[1]))
    call FF_E2E_Kill(FF_E2E_hero, CreateUnit(Player(0), 'hfoo', x + 100.0, y, 0.0))
    call FF_E2E_Kill(FF_E2E_hero, CreateUnit(Player(1), 'hfoo', x + 100.0, y + 100.0, 0.0))
    call FF_E2E_Kill(FF_E2E_hero, CreateUnit(Player(3), 'hfoo', x + 100.0, y - 100.0, 0.0))
    call FF_E2E_Kill(FF_E2E_hero, udg_herO[4])
    call FF_E2E_After(2.0, function FF_E2E_FfaKillsRead)
endfunction

// --- chat commands ----------------------------------------------------------------------------------------------

function FF_E2E_FfaZoom takes nothing returns nothing
    call FF_E2E_Row("zoom,after=" + FF_E2E_R2S(GetCameraField(CAMERA_FIELD_TARGET_DISTANCE)))
    call FF_E2E_FfaKills()
endfunction

function FF_E2E_FfaCam takes nothing returns nothing
    call FF_E2E_WaitChat("-zoom 3500", function FF_E2E_FfaZoom)
endfunction

function FF_E2E_FfaTime takes nothing returns nothing
    call FF_E2E_WaitChat("-cam", function FF_E2E_FfaCam)
endfunction

function FF_E2E_FfaKd takes nothing returns nothing
    call FF_E2E_WaitChat("-time", function FF_E2E_FfaTime)
endfunction

// --- purchases, research, upgrades -----------------------------------------------------------------------------

function FF_E2E_FfaBuysRead takes nothing returns nothing
    call FF_E2E_Row("bought,item=" + FF_E2E_Bool(UnitHasItemOfTypeBJ(FF_E2E_hero, FF_E2E_item)) + ",n00Q=" + I2S(FF_E2E_CountOf(Player(0), 'n00Q')) + ",Rhme=" + I2S(GetPlayerTechCount(Player(0), 'Rhme', true)) + ",Rhar=" + I2S(GetPlayerTechCount(Player(0), 'Rhar', true)) + ",R001=" + I2S(GetPlayerTechCount(Player(0), 'R001', true)) + ",hgtw=" + I2S(FF_E2E_CountOf(Player(0), 'hgtw')) + ",gold=" + I2S(FF_E2E_Gold(1)))
    call FF_E2E_WaitChat("-kd", function FF_E2E_FfaKd)
endfunction

function FF_E2E_FfaResearch2 takes nothing returns nothing
    call FF_E2E_Row("research,o2=" + FF_E2E_Bool(IssueImmediateOrderById(udg_base[1], 'Rhme')))
    call FF_E2E_After(20.0, function FF_E2E_FfaBuysRead)
endfunction

function FF_E2E_FfaResearch takes nothing returns nothing
    local unit base = udg_base[1]
    local unit up = FF_E2E_Nearest(Player(0), 'n003', GetUnitX(base), GetUnitY(base))
    local unit tower = FF_E2E_Nearest(Player(0), 'hwtw', GetUnitX(base), GetUnitY(base))
    call FF_E2E_Row("creep,n00Q=" + I2S(FF_E2E_CountOf(Player(0), 'n00Q')))
    call FF_E2E_Row("research,base=" + FF_us_Id2S(GetUnitTypeId(base)) + ",n003=" + FF_E2E_Bool(up != null) + ",hwtw=" + FF_E2E_Bool(tower != null) + ",o1=" + FF_E2E_Bool(IssueImmediateOrderById(base, 'Rhme')) + ",o3=" + FF_E2E_Bool(IssueImmediateOrderById(base, 'Rhar')) + ",o4=" + FF_E2E_Bool(IssueImmediateOrderById(up, 'R001')) + ",o5=" + FF_E2E_Bool(IssueImmediateOrderById(tower, 'hgtw')))
    // research times are seconds (4s + 1/level; R001 5s), the scout -> guard tower upgrade likewise short; a
    // research's next level can't be queued while one runs: attack level 2 in FF_E2E_FfaResearch2
    call FF_E2E_After(20.0, function FF_E2E_FfaResearch2)
    set base = null
    set up = null
    set tower = null
endfunction

function FF_E2E_FfaCreep takes nothing returns nothing
    local real sx = GetStartLocationX(GetPlayerStartLocation(Player(0)))
    local real sy = GetStartLocationY(GetPlayerStartLocation(Player(0)))
    local unit shop = FF_E2E_Nearest(Player(PLAYER_NEUTRAL_PASSIVE), 'n00R', sx, sy)
    if shop == null then
        call FF_E2E_Row("creep,shop=0")
    else
        call SetUnitPosition(FF_E2E_hero, GetUnitX(shop) + 150.0, GetUnitY(shop) - 150.0)
        call FF_E2E_Row("creep,shop=" + FF_E2E_R2S(GetUnitX(shop)) + ":" + FF_E2E_R2S(GetUnitY(shop)) + ",order=" + FF_E2E_Bool(IssueNeutralImmediateOrderById(Player(0), shop, 'n00Q')))
    endif
    call FF_E2E_After(2.0, function FF_E2E_FfaResearch)
    set shop = null
endfunction

function FF_E2E_FfaItemBuy takes nothing returns nothing
    set FF_E2E_item = FF_E2E_soldItem
    call FF_E2E_Row("item,via=key,id=" + FF_us_Id2S(FF_E2E_item) + ",has=" + FF_E2E_Bool(FF_E2E_item != 0 and UnitHasItemOfTypeBJ(FF_E2E_hero, FF_E2E_item)) + ",t=" + I2S(FF_E2E_Now()))
    if FF_E2E_item == 0 then
        call FF_E2E_FfaBuyItem()
    endif
    call SetUnitInvulnerable(FF_E2E_hero, true)
    if GetLocalPlayer() == Player(0) then
        call ClearSelection()
        call SelectUnit(FF_E2E_hero, true)
    endif
    call FF_E2E_After(1.0, function FF_E2E_FfaCreep)
endfunction

function FF_E2E_FfaItem takes nothing returns nothing
    local integer i = 1
    local string h = "hero"
    loop
        exitwhen i > 12
        set h = h + "," + I2S(i) + "=" + FF_us_Id2S(GetUnitTypeId(udg_herO[i]))
        set i = i + 1
    endloop
    call FF_E2E_Row(h)
    set FF_E2E_hero = udg_herO[1]
    call SetUnitInvulnerable(FF_E2E_hero, true)
    call SetPlayerState(Player(0), PLAYER_STATE_RESOURCE_GOLD, 20000)
    // Transmute is the Alchemist's ultimate (hero level 6)
    call SetHeroLevel(FF_E2E_hero, 6, false)
    call SelectHeroSkill(FF_E2E_hero, 'ANtm')
    call FF_E2E_Row("skill,ANtm=" + I2S(GetUnitAbilityLevel(FF_E2E_hero, 'ANtm')))
    call FF_E2E_BuyByKey(FF_E2E_hero, gg_unit_n01B_0055, function FF_E2E_FfaItemBuy)
endfunction

// The host's game-type dialog: "Pub Game Default", the first of the main map's four buttons.
function FF_E2E_HostClick takes nothing returns string
    return "0.5 0.478"
endfunction

function FF_E2E_Scenario takes nothing returns nothing
    local integer i = 1
    local trigger t = CreateTrigger()
    call FF_E2E_Begin("ffa")
    call TriggerRegisterAnyUnitEventBJ(t, EVENT_PLAYER_UNIT_SPELL_EFFECT)
    call TriggerAddAction(t, function FF_E2E_FfaOnSpell)
    set FF_E2E_tmCastCode = function FF_E2E_FfaTmCast
    call CreateUnit(Player(0), 'N01C', -2600.0, -300.0, 0.0)
    loop
        exitwhen i >= 12
        call CreateUnit(Player(i), 'H005', -2600.0, -300.0, 0.0)
        set i = i + 1
    endloop
    call FF_E2E_After(3.0, function FF_E2E_FfaItem)
    set t = null
endfunction
