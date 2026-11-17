// e2e scenario "transmute_creeps" (main and Solo): which Transmutes count as tm_creeps, through real sales at the
// creep shops and real Transmute projectiles, with the client as slot 1 (the Alchemist, N01C) and two enemy sides
// A and B (main: slots 4 and 7, one per enemy team; Solo: slots 5 and 8), all at the empty map centre.
//   t~3     every seat gets a hero in the tavern area (slot 1 the Alchemist, level 6, Transmute learned)
//   hires   A and B each hire two n00A (level 3; Transmute takes creeps up to level 6-8, not the level-10 Turtle)
//           through a real sale at an east creep shop (`hire,n=..`; the west shops refuse the scripted order);
//           test setup only: the creep is put back into the shop's stock before each sale, and A and B get Solo's
//           tier-1 tech (R00D), without which Solo's shops refuse orders until 90 s
//   cases   one Transmute each (`tc,case=<n>,when=0|1,...` before/after; every death in a case: `death,...`):
//           1 lands on a hired n00A of A        -> a hit and a tm_creeps
//           2 lands on an n00A nobody hired     -> a hit only (the mark is the sale, not the unit type)
//           3 lands on a footman of A          -> a hit only
//           4 a hired n00A of B, killed by B's own footman while the projectile flies -> denied, a save for B
//           5 a hired n00A of A, removed while the projectile flies -> dodged: a cast only
//           6 no Transmute: slot 1's hero kills a hired n00A of B -> nothing; it leaves the hired group
//   end     the stats rows, the kill log and the counters in one tick (`tcsnap`), the game paused, END
// tests/e2e/check_e2e.py (check_transmute_creeps) judges it all.

globals
    unit FF_E2E_tcHero = null
    integer FF_E2E_tcA = 0
    integer FF_E2E_tcB = 0
    unit array FF_E2E_tcHired
    integer FF_E2E_tcHiredN = 0
    integer FF_E2E_tcCase = 0
    unit FF_E2E_tcTarget = null
    unit FF_E2E_tcKiller = null
    integer FF_E2E_tcTries = 0
    code FF_E2E_tcNextCode = null
endglobals

// --- records ---------------------------------------------------------------------------------------------------

function FF_E2E_TcCounters takes nothing returns string
    return ",casts=" + I2S(FF_st_tmCasts[1]) + ",hits=" + I2S(FF_st_tmHits[1]) + ",creeps=" + I2S(FF_st_tmCreeps[1]) + ",denied=" + I2S(FF_st_tmDenied[1]) + ",savesA=" + I2S(FF_st_tmSaves[FF_E2E_tcA]) + ",savesB=" + I2S(FF_st_tmSaves[FF_E2E_tcB]) + ",creepsA=" + I2S(FF_st_tmCreeps[FF_E2E_tcA]) + ",creepsB=" + I2S(FF_st_tmCreeps[FF_E2E_tcB]) + ",hired=" + I2S(CountUnitsInGroup(FF_st_hired))
endfunction

function FF_E2E_TcRecord takes integer when returns nothing
    call FF_E2E_Row("tc,case=" + I2S(FF_E2E_tcCase) + ",when=" + I2S(when) + ",t=" + I2S(FF_E2E_Now()) + FF_E2E_TcCounters())
endfunction

// Every death while a case runs: who died and the killer the engine names (owner slot, type), or none.
function FF_E2E_TcOnDeath takes nothing returns nothing
    local unit v = GetTriggerUnit()
    local unit k = GetKillingUnit()
    local string ks = "none"
    if FF_E2E_tcCase != 0 then
        if k != null then
            set ks = I2S(GetPlayerId(GetOwningPlayer(k)) + 1) + ",ktype=" + FF_us_Id2S(GetUnitTypeId(k))
        endif
        call FF_E2E_Row("death,case=" + I2S(FF_E2E_tcCase) + ",victim=" + I2S(GetPlayerId(GetOwningPlayer(v)) + 1) + ",vtype=" + FF_us_Id2S(GetUnitTypeId(v)) + ",target=" + FF_E2E_Bool(v == FF_E2E_tcTarget) + ",killer=" + ks)
    endif
    set v = null
    set k = null
endfunction

// --- the cases -------------------------------------------------------------------------------------------------

// Paused at distance d east of the hero: no wandering, no attacks, still a valid target.
function FF_E2E_TcPlace takes unit u, real d returns unit
    call SetUnitPosition(u, GetUnitX(FF_E2E_tcHero) + d, GetUnitY(FF_E2E_tcHero))
    call PauseUnit(u, true)
    return u
endfunction

function FF_E2E_TcNew takes integer slot, integer id, real d returns unit
    return FF_E2E_TcPlace(CreateUnit(Player(slot - 1), id, GetUnitX(FF_E2E_tcHero) + d, GetUnitY(FF_E2E_tcHero), 180.0), d)
endfunction

// Runs on our hero's Transmute (after the stats addon registered the cast: its trigger is older).
function FF_E2E_TcOnSpell takes nothing returns nothing
    if GetTriggerUnit() != FF_E2E_tcHero or GetSpellAbilityId() != 'ANtm' then
        return
    endif
    call FF_E2E_Row("effect,case=" + I2S(FF_E2E_tcCase) + ",target=" + FF_E2E_Bool(GetSpellTargetUnit() == FF_E2E_tcTarget) + ",t=" + I2S(FF_E2E_Now()))
    if FF_E2E_tcCase == 4 then
        // the projectile has just left: the target's own side kills it first
        call FF_E2E_Kill(FF_E2E_tcKiller, FF_E2E_tcTarget)
    elseif FF_E2E_tcCase == 5 then
        // gone before the projectile lands: no death, so the stats addon's 4 s expiry counts it as dodged
        call RemoveUnit(FF_E2E_tcTarget)
    endif
endfunction

// The counters after (the dodge expires 4 s after the cast); then the next case.
function FF_E2E_TcRead takes nothing returns nothing
    call FF_E2E_TcRecord(1)
    if FF_E2E_tcKiller != null then
        call RemoveUnit(FF_E2E_tcKiller)
        set FF_E2E_tcKiller = null
    endif
    call FF_E2E_After(1.0, FF_E2E_tcNextCode)
endfunction

// The cast order, again every second while the hero refuses it (it can refuse a cast 6 s after the previous one).
function FF_E2E_TcOrder takes nothing returns nothing
    local boolean ok
    call UnitResetCooldown(FF_E2E_tcHero)
    call SetUnitState(FF_E2E_tcHero, UNIT_STATE_MANA, GetUnitState(FF_E2E_tcHero, UNIT_STATE_MAX_MANA))
    set ok = IssueTargetOrder(FF_E2E_tcHero, "transmute", FF_E2E_tcTarget)
    set FF_E2E_tcTries = FF_E2E_tcTries + 1
    if not ok and FF_E2E_tcTries < 10 then
        call FF_E2E_After(1.0, function FF_E2E_TcOrder)
        return
    endif
    call FF_E2E_Row("cast,case=" + I2S(FF_E2E_tcCase) + ",order=" + FF_E2E_Bool(ok) + ",tries=" + I2S(FF_E2E_tcTries) + ",level=" + I2S(GetUnitLevel(FF_E2E_tcTarget)))
    call FF_E2E_After(6.0, function FF_E2E_TcRead)
endfunction

// Starts case n on `target` (the counters before, with whether the target is in the hired group); `next` follows.
function FF_E2E_TcBegin takes integer n, unit target, code next returns nothing
    set FF_E2E_tcCase = n
    set FF_E2E_tcTarget = target
    set FF_E2E_tcNextCode = next
    set FF_E2E_tcTries = 0
    call FF_E2E_TcRecord(0)
    call FF_E2E_Row("target,case=" + I2S(n) + ",owner=" + I2S(GetPlayerId(GetOwningPlayer(target)) + 1) + ",type=" + FF_us_Id2S(GetUnitTypeId(target)) + ",inhired=" + FF_E2E_Bool(IsUnitInGroup(target, FF_st_hired)))
endfunction

// --- the end: stats rows, kill log and the counters in one tick ------------------------------------------------

function FF_E2E_TcSnapshot takes nothing returns nothing
    local integer i = 1
    local string a = "tcsnap,part=1"
    local string b = "tcsnap,part=2"
    set FF_E2E_tcCase = 0
    call FF_kl_Flush()
    call FF_gr_RefreshStats()
    call FF_gr_Flush()
    loop
        exitwhen i > 12
        if i <= 6 then
            set a = a + ",uk" + I2S(i) + "=" + I2S(udg_unit_kills[i]) + ",hk" + I2S(i) + "=" + I2S(udg_hero_kills[i]) + ",ud" + I2S(i) + "=" + I2S(udg_unit_deaths[i]) + ",hd" + I2S(i) + "=" + I2S(udg_hero_deaths[i])
        else
            set b = b + ",uk" + I2S(i) + "=" + I2S(udg_unit_kills[i]) + ",hk" + I2S(i) + "=" + I2S(udg_hero_kills[i]) + ",ud" + I2S(i) + "=" + I2S(udg_unit_deaths[i]) + ",hd" + I2S(i) + "=" + I2S(udg_hero_deaths[i])
        endif
        set i = i + 1
    endloop
    call FF_E2E_Row(a)
    call FF_E2E_Row(b)
    // frozen until the runner closes the game: on Solo the mass reaches the centre now, and a later flush would
    // write kills the snapshot never saw
    call PauseGame(true)
    call FF_E2E_Done()
endfunction

function FF_E2E_TcCase6 takes nothing returns nothing
    call FF_E2E_TcBegin(6, FF_E2E_TcPlace(FF_E2E_tcHired[3], 350.0), function FF_E2E_TcSnapshot)
    call FF_E2E_Kill(FF_E2E_tcHero, FF_E2E_tcTarget)
    call FF_E2E_After(2.0, function FF_E2E_TcRead)
endfunction

function FF_E2E_TcCase5 takes nothing returns nothing
    call FF_E2E_TcBegin(5, FF_E2E_TcPlace(FF_E2E_tcHired[1], 350.0), function FF_E2E_TcCase6)
    call FF_E2E_TcOrder()
endfunction

function FF_E2E_TcCase4 takes nothing returns nothing
    call FF_E2E_TcBegin(4, FF_E2E_TcPlace(FF_E2E_tcHired[2], 350.0), function FF_E2E_TcCase5)
    set FF_E2E_tcKiller = FF_E2E_TcNew(FF_E2E_tcB, 'hfoo', 450.0)
    call FF_E2E_TcOrder()
endfunction

function FF_E2E_TcCase3 takes nothing returns nothing
    call FF_E2E_TcBegin(3, FF_E2E_TcNew(FF_E2E_tcA, 'hfoo', 350.0), function FF_E2E_TcCase4)
    call FF_E2E_TcOrder()
endfunction

function FF_E2E_TcCase2 takes nothing returns nothing
    call FF_E2E_TcBegin(2, FF_E2E_TcNew(FF_E2E_tcA, 'n00A', 350.0), function FF_E2E_TcCase3)
    call FF_E2E_TcOrder()
endfunction

function FF_E2E_TcCase1 takes nothing returns nothing
    call FF_E2E_TcBegin(1, FF_E2E_TcPlace(FF_E2E_tcHired[0], 350.0), function FF_E2E_TcCase2)
    call FF_E2E_TcOrder()
endfunction

// --- hires -----------------------------------------------------------------------------------------------------

function FF_E2E_TcOnSell takes nothing returns nothing
    if GetUnitTypeId(GetSoldUnit()) == 'n00A' and FF_E2E_tcHiredN < 4 then
        set FF_E2E_tcHired[FF_E2E_tcHiredN] = GetSoldUnit()
        set FF_E2E_tcHiredN = FF_E2E_tcHiredN + 1
    endif
endfunction

// The sale is counted one tick after it: every creep sold, and whether the stats addon marked it as hired.
function FF_E2E_TcHired takes nothing returns nothing
    local integer i = 0
    local string s = "hired,n=" + I2S(FF_E2E_tcHiredN)
    loop
        exitwhen i >= FF_E2E_tcHiredN
        set s = s + ",owner" + I2S(i) + "=" + I2S(GetPlayerId(GetOwningPlayer(FF_E2E_tcHired[i])) + 1) + ",in" + I2S(i) + "=" + FF_E2E_Bool(IsUnitInGroup(FF_E2E_tcHired[i], FF_st_hired)) + ",alive" + I2S(i) + "=" + FF_E2E_Bool(FF_UnitAlive(FF_E2E_tcHired[i]))
        set i = i + 1
    endloop
    call FF_E2E_Row(s + ",creepsA=" + I2S(FF_st_creeps[FF_E2E_tcA]) + ",creepsB=" + I2S(FF_st_creeps[FF_E2E_tcB]) + ",group=" + I2S(CountUnitsInGroup(FF_st_hired)))
    if FF_E2E_tcHiredN < 4 then
        call FF_E2E_Done()
        return
    endif
    call FF_E2E_TcCase1()
endfunction

// Sale i (0..3) at the shop nearest (cx, cy): A buys the first two, B the last two, with a hero of its own beside it.
function FF_E2E_TcBuy takes integer i, real cx, real cy returns nothing
    local integer slot = FF_E2E_tcA
    local unit shop = FF_E2E_Nearest(Player(PLAYER_NEUTRAL_PASSIVE), 'n00R', cx, cy)
    local unit buyer
    if i >= 2 then
        set slot = FF_E2E_tcB
    endif
    if shop == null then
        call FF_E2E_Row("hire,n=" + I2S(i) + ",shop=0")
        return
    endif
    set buyer = CreateUnit(Player(slot - 1), 'H005', GetUnitX(shop) + 150.0, GetUnitY(shop) - 150.0, 0.0)
    call SetUnitInvulnerable(buyer, true)
    call AddUnitToStock(shop, 'n00A', 1, 1)
    call FF_E2E_Row("hire,n=" + I2S(i) + ",slot=" + I2S(slot) + ",shop=" + I2S(R2I(GetUnitX(shop))) + ":" + I2S(R2I(GetUnitY(shop))) + ",buyer=" + I2S(R2I(GetUnitX(buyer))) + ":" + I2S(R2I(GetUnitY(buyer))) + ",order=" + FF_E2E_Bool(IssueNeutralImmediateOrderById(Player(slot - 1), shop, 'n00A')))
    call RemoveUnit(buyer)
    set shop = null
    set buyer = null
endfunction

function FF_E2E_TcHire takes nothing returns nothing
    call SetPlayerState(Player(FF_E2E_tcA - 1), PLAYER_STATE_RESOURCE_GOLD, 20000)
    call SetPlayerState(Player(FF_E2E_tcB - 1), PLAYER_STATE_RESOURCE_GOLD, 20000)
    call SetPlayerTechResearched(Player(FF_E2E_tcA - 1), 'R00D', 1)
    call SetPlayerTechResearched(Player(FF_E2E_tcB - 1), 'R00D', 1)
    call FF_E2E_TcBuy(0, 3264.0, 3008.0)
    call FF_E2E_TcBuy(1, 3264.0, 3008.0)
    call FF_E2E_TcBuy(2, 3264.0, -3520.0)
    call FF_E2E_TcBuy(3, 3264.0, -3520.0)
    call FF_E2E_After(1.0, function FF_E2E_TcHired)
endfunction

// --- start ------------------------------------------------------------------------------------------------------

function FF_E2E_TcHero takes nothing returns nothing
    call FF_E2E_Row("hero,slot1=" + FF_us_Id2S(GetUnitTypeId(udg_herO[1])) + ",ours=" + FF_E2E_Bool(udg_herO[1] == FF_E2E_tcHero) + ",A=" + I2S(FF_E2E_tcA) + ",B=" + I2S(FF_E2E_tcB))
    call SetUnitInvulnerable(FF_E2E_tcHero, true)
    // Transmute is the Alchemist's ultimate (hero level 6)
    call SetHeroLevel(FF_E2E_tcHero, 6, false)
    call SelectHeroSkill(FF_E2E_tcHero, 'ANtm')
    call SetUnitPosition(FF_E2E_tcHero, 0.0, -256.0)
    call FF_E2E_Row("skill,ANtm=" + I2S(GetUnitAbilityLevel(FF_E2E_tcHero, 'ANtm')))
    call FF_E2E_TcHire()
endfunction

function FF_E2E_HostClick takes nothing returns string
    return ""
endfunction

function FF_E2E_Scenario takes nothing returns nothing
    local integer i = 1
    local trigger t
    call FF_E2E_Begin("transmute_creeps")
    // main: slots 4 and 7 (teams 2 and 3); Solo (seats 1, 5, 8, 12): slots 5 and 8
    if GetPlayerSlotState(Player(3)) == PLAYER_SLOT_STATE_PLAYING then
        set FF_E2E_tcA = 4
        set FF_E2E_tcB = 7
    else
        set FF_E2E_tcA = 5
        set FF_E2E_tcB = 8
    endif
    set t = CreateTrigger()
    call TriggerRegisterAnyUnitEventBJ(t, EVENT_PLAYER_UNIT_SPELL_EFFECT)
    call TriggerAddAction(t, function FF_E2E_TcOnSpell)
    set t = CreateTrigger()
    call TriggerRegisterAnyUnitEventBJ(t, EVENT_PLAYER_UNIT_DEATH)
    call TriggerAddAction(t, function FF_E2E_TcOnDeath)
    set t = CreateTrigger()
    call TriggerRegisterAnyUnitEventBJ(t, EVENT_PLAYER_UNIT_SELL)
    call TriggerAddAction(t, function FF_E2E_TcOnSell)
    // every seat gets the hero the map expects (udg_herO), created in the tavern area like the kd scenario
    set FF_E2E_tcHero = CreateUnit(Player(0), 'N01C', -2600.0, -300.0, 0.0)
    loop
        exitwhen i >= 12
        if GetPlayerSlotState(Player(i)) == PLAYER_SLOT_STATE_PLAYING then
            call CreateUnit(Player(i), 'H005', -2600.0, -300.0, 0.0)
        endif
        set i = i + 1
    endloop
    call FF_E2E_After(3.0, function FF_E2E_TcHero)
    set t = null
endfunction
