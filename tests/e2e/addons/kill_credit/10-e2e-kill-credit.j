// e2e scenario "kill_credit": enemy heroes killed by a killer that is dead, or a spell dummy, by the time the damage
// lands, through real game actions, with the client as player 1 (slot 1, a participant; slots 2-12 are computers —
// `slots` file), all before Mass START (~98s) at the empty map centre. Each kill must count for slot 1 in the map's
// own counters (the kill-credit hooks in scripting/jass-main/anchors.txt).
//   1 coin factory: a moneybag's Kaboom (it dies in its own blast)   4 Elemental Hellfire: a Flame Strike tick
//   2 Objection: a Soul Burn tick, after the dummy's old 0.10 s life 5 Jaina's ultimate: a Rain of Fire burn tick,
//   3 Parasite: a Parasite tick, after the dummy's old 0.10 s life      after the orbs vanished
//                                                                    6 Thor's Mjolnir: the hammer's Firebolt
// Each case records the counters, slot 1's gold and the caster's XP right before and after
// (`kc,case=<n>,when=0|1,...`), every death with the killer the engine names (`death,...`), and the victim's fate
// (`end,case=<n>,died=0|1,secs=`). The victim is a slot-4 hero with 100000 life until the moment only the tested
// damage can still hit it, then 1. Afterwards the kill log, the stats rows and the counters are written in one tick
// (`kcsnap`). tests/e2e/check_e2e.py (check_kill_credit) judges it all.

globals
    integer FF_E2E_kcCase = 0
    unit FF_E2E_kcCaster = null
    unit FF_E2E_kcVictim = null
    unit FF_E2E_kcThorOld = null
    unit FF_E2E_kcBag = null
    integer FF_E2E_kcWaited = 0
    code FF_E2E_kcNextCode = null
endglobals

function FF_E2E_KcCounters takes integer slot returns string
    return ",uk" + I2S(slot) + "=" + I2S(udg_unit_kills[slot]) + ",hk" + I2S(slot) + "=" + I2S(udg_hero_kills[slot]) + ",ud" + I2S(slot) + "=" + I2S(udg_unit_deaths[slot]) + ",hd" + I2S(slot) + "=" + I2S(udg_hero_deaths[slot])
endfunction

function FF_E2E_KcRecord takes integer when returns nothing
    call FF_E2E_Row("kc,case=" + I2S(FF_E2E_kcCase) + ",when=" + I2S(when) + FF_E2E_KcCounters(1) + FF_E2E_KcCounters(4) + ",gold1=" + I2S(GetPlayerState(Player(0), PLAYER_STATE_RESOURCE_GOLD)) + ",xp=" + I2S(GetHeroXP(FF_E2E_kcCaster)))
endfunction

// Every death while a case runs: who died and the killer the engine names (owner slot, alive, type), or none.
function FF_E2E_KcOnDeath takes nothing returns nothing
    local unit v = GetTriggerUnit()
    local unit k = GetKillingUnit()
    local string ks = "none"
    if FF_E2E_kcCase != 0 then
        if k != null then
            set ks = I2S(GetPlayerId(GetOwningPlayer(k)) + 1) + ",kalive=" + FF_E2E_Bool(FF_UnitAlive(k)) + ",ktype=" + FF_us_Id2S(GetUnitTypeId(k))
        endif
        call FF_E2E_Row("death,case=" + I2S(FF_E2E_kcCase) + ",victim=" + I2S(GetPlayerId(GetOwningPlayer(v)) + 1) + ",vtype=" + FF_us_Id2S(GetUnitTypeId(v)) + ",killer=" + ks)
    endif
    set v = null
    set k = null
endfunction

// --- building blocks -------------------------------------------------------------------------------------------

// A slot-1 hero of type `id` at (x, y) that never attacks (Abun) and has the mana for any cast.
function FF_E2E_KcCaster takes integer id, real x, real y returns unit
    local unit u = CreateUnit(Player(0), id, x, y, 0.0)
    call UnitAddAbility(u, 'Abun')
    call BlzSetUnitMaxMana(u, 100000)
    call SetUnitState(u, UNIT_STATE_MANA, 100000.0)
    call SetUnitInvulnerable(u, true)
    set FF_E2E_kcCaster = u
    set u = null
    return FF_E2E_kcCaster
endfunction

// Gives the caster ability `abil` at `level`.
function FF_E2E_KcSkill takes integer abil, integer level returns nothing
    call UnitAddAbility(FF_E2E_kcCaster, abil)
    call SetUnitAbilityLevel(FF_E2E_kcCaster, abil, level)
endfunction

// The slot-4 victim hero at (x, y) with `life` (of 100000): unpaused (paused units take no damage-over-time), on
// hold position and without an attack, so only the case's damage can kill it.
function FF_E2E_KcVictimAt takes real x, real y, real life returns unit
    set FF_E2E_kcVictim = CreateUnit(Player(3), 'H005', x, y, 180.0)
    call UnitAddAbility(FF_E2E_kcVictim, 'Abun')
    call BlzSetUnitMaxHP(FF_E2E_kcVictim, 100000)
    call SetUnitState(FF_E2E_kcVictim, UNIT_STATE_LIFE, life)
    call IssueImmediateOrder(FF_E2E_kcVictim, "holdposition")
    return FF_E2E_kcVictim
endfunction

function FF_E2E_KcCast takes boolean ok returns nothing
    call FF_E2E_Row("cast,case=" + I2S(FF_E2E_kcCase) + ",order=" + FF_E2E_Bool(ok))
endfunction

// From now on only the tested damage can still hit the victim: one more tick kills it.
function FF_E2E_KcLow takes nothing returns nothing
    if FF_UnitAlive(FF_E2E_kcVictim) then
        call SetUnitState(FF_E2E_kcVictim, UNIT_STATE_LIFE, 1.0)
    endif
endfunction

// The counters after; then the case's units leave so they can't reach into the next case.
function FF_E2E_KcRead takes nothing returns nothing
    call FF_E2E_KcRecord(1)
    if FF_UnitAlive(FF_E2E_kcVictim) then
        call RemoveUnit(FF_E2E_kcVictim)
    endif
    if FF_E2E_kcCase != 6 then
        call RemoveUnit(FF_E2E_kcCaster)
    endif
    call FF_E2E_After(1.0, FF_E2E_kcNextCode)
endfunction

// Waits up to 12s for the victim to die, then reads the counters a second later.
function FF_E2E_KcWait takes nothing returns nothing
    if FF_UnitAlive(FF_E2E_kcVictim) and FF_E2E_kcWaited < 24 then
        set FF_E2E_kcWaited = FF_E2E_kcWaited + 1
        call FF_E2E_After(0.5, function FF_E2E_KcWait)
        return
    endif
    call FF_E2E_Row("end,case=" + I2S(FF_E2E_kcCase) + ",died=" + FF_E2E_Bool(not FF_UnitAlive(FF_E2E_kcVictim)) + ",secs=" + FF_E2E_R2S(FF_E2E_kcWaited * 0.5))
    call FF_E2E_After(1.0, function FF_E2E_KcRead)
endfunction

// Starts case `n` (the counters before), `next` runs after its read.
function FF_E2E_KcBegin takes integer n, code next returns nothing
    set FF_E2E_kcCase = n
    set FF_E2E_kcNextCode = next
    set FF_E2E_kcWaited = 0
    call FF_E2E_KcRecord(0)
endfunction

// --- the end: kill log, stats and the counters in one tick -----------------------------------------------------

function FF_E2E_KcSnapshot takes nothing returns nothing
    local integer i = 1
    local string a = "kcsnap,part=1"
    local string b = "kcsnap,part=2"
    set FF_E2E_kcCase = 0
    set udg_herO[1] = FF_E2E_kcThorOld
    call FF_kl_Flush()
    call FF_gr_RefreshStats()
    call FF_gr_Flush()
    loop
        exitwhen i > 12
        if i <= 6 then
            set a = a + FF_E2E_KcCounters(i)
        else
            set b = b + FF_E2E_KcCounters(i)
        endif
        set i = i + 1
    endloop
    call FF_E2E_Row(a)
    call FF_E2E_Row(b)
    call FF_E2E_Done()
endfunction

// --- the cases -------------------------------------------------------------------------------------------------

// Thor's Mjolnir (A0EC, level 6: the swarm itself deals 0): the map moves the hammer only for a player whose hero
// (udg_herO) is Thor, so the caster takes slot 1's hero place for this case. The hammer hits the victim (life 1)
// and its Firebolt missile kills it.
function FF_E2E_KcCase6 takes nothing returns nothing
    call FF_E2E_KcBegin(6, function FF_E2E_KcSnapshot)
    call FF_E2E_KcCaster('H048', 500.0, 600.0)
    call FF_E2E_KcSkill('A0EC', 6)
    set FF_E2E_kcThorOld = udg_herO[1]
    set udg_herO[1] = FF_E2E_kcCaster
    call FF_E2E_KcVictimAt(800.0, 600.0, 1.0)
    call FF_E2E_KcCast(IssuePointOrder(FF_E2E_kcCaster, "carrionswarm", 800.0, 600.0))
    call FF_E2E_After(0.5, function FF_E2E_KcWait)
endfunction

// Jaina's ultimate (A048, level 3): the fire orb's Rain of Fire wave sets the victim burning; the orbs vanish 4s
// after the cast, then the victim drops to 1 life and the burn (5s) kills it.
function FF_E2E_KcCase5 takes nothing returns nothing
    call FF_E2E_KcBegin(5, function FF_E2E_KcCase6)
    call FF_E2E_KcCaster('H005', -800.0, 600.0)
    call FF_E2E_KcSkill('A048', 3)
    call FF_E2E_KcVictimAt(-500.0, 600.0, 100000.0)
    call FF_E2E_KcCast(IssuePointOrder(FF_E2E_kcCaster, "blizzard", -500.0, 600.0))
    call FF_E2E_After(4.5, function FF_E2E_KcLow)
    call FF_E2E_After(4.6, function FF_E2E_KcWait)
endfunction

// Elemental Hellfire (A0CC, level 1): six Flame Strikes in a ring 225 around the caster (one at 0 degrees, where
// the victim stands); 3.6s in (the dummies lived 4s), the victim drops to 1 life.
function FF_E2E_KcCase4 takes nothing returns nothing
    call FF_E2E_KcBegin(4, function FF_E2E_KcCase5)
    call FF_E2E_KcCaster('H005', -1500.0, 600.0)
    call FF_E2E_KcSkill('A0CC', 1)
    call FF_E2E_KcVictimAt(-1275.0, 600.0, 100000.0)
    call FF_E2E_KcCast(IssueImmediateOrder(FF_E2E_kcCaster, "creepthunderclap"))
    call FF_E2E_After(3.6, function FF_E2E_KcLow)
    call FF_E2E_After(3.7, function FF_E2E_KcWait)
endfunction

// Parasite (A05E, level 1): the dummy's Parasite (A0HL, 3s on heroes); 1.5s in, the victim drops to 1 life.
function FF_E2E_KcCase3 takes nothing returns nothing
    call FF_E2E_KcBegin(3, function FF_E2E_KcCase4)
    call FF_E2E_KcCaster('H005', 300.0, -256.0)
    call FF_E2E_KcSkill('A05E', 1)
    call FF_E2E_KcVictimAt(500.0, -256.0, 100000.0)
    call FF_E2E_KcCast(IssueTargetOrder(FF_E2E_kcCaster, "unholyfrenzy", FF_E2E_kcVictim))
    call FF_E2E_After(1.5, function FF_E2E_KcLow)
    call FF_E2E_After(1.6, function FF_E2E_KcWait)
endfunction

// Objection (A0M1, level 6) on an enemy: the dummy's Soul Burn (6.5s on heroes); 1.5s in, the victim drops to 1.
function FF_E2E_KcCase2 takes nothing returns nothing
    call FF_E2E_KcBegin(2, function FF_E2E_KcCase3)
    call FF_E2E_KcCaster('O00O', -700.0, -256.0)
    call FF_E2E_KcSkill('A0M1', 6)
    call FF_E2E_KcVictimAt(-500.0, -256.0, 100000.0)
    call FF_E2E_KcCast(IssueTargetOrder(FF_E2E_kcCaster, "unholyfrenzy", FF_E2E_kcVictim))
    call FF_E2E_After(1.5, function FF_E2E_KcLow)
    call FF_E2E_After(1.6, function FF_E2E_KcWait)
endfunction

// Coin factory: a slot-1 moneybag (n02W) next to the victim (life 1) is ordered to Kaboom it. A slot-1 hero watches
// nearby (its XP shows the engine's hero-kill XP).
function FF_E2E_KcBagTrace takes nothing returns nothing
    if FF_E2E_kcCase == 1 then
        call FF_E2E_Row("bag,case=1,alive=" + FF_E2E_Bool(FF_UnitAlive(FF_E2E_kcBag)) + ",x=" + I2S(R2I(GetUnitX(FF_E2E_kcBag))) + ",y=" + I2S(R2I(GetUnitY(FF_E2E_kcBag))) + ",order=" + OrderId2String(GetUnitCurrentOrder(FF_E2E_kcBag)) + ",kab=" + I2S(GetUnitAbilityLevel(FF_E2E_kcBag, 'A0GR')) + ",vx=" + I2S(R2I(GetUnitX(FF_E2E_kcVictim))) + ",vy=" + I2S(R2I(GetUnitY(FF_E2E_kcVictim))))
        call FF_E2E_After(0.5, function FF_E2E_KcBagTrace)
    endif
endfunction

function FF_E2E_KcBagOrder takes nothing returns nothing
    call FF_E2E_KcCast(IssueTargetOrder(FF_E2E_kcBag, "selfdestruct", FF_E2E_kcVictim))
endfunction

function FF_E2E_KcCase1 takes nothing returns nothing
    call FF_E2E_KcBegin(1, function FF_E2E_KcCase2)
    call FF_E2E_KcCaster('H005', -1700.0, -256.0)
    set FF_E2E_kcBag = CreateUnit(Player(0), 'n02W', -1580.0, -256.0, 0.0)
    // the map centre has no room for a moneybag: the game would place it ~1000 away; put it next to the victim
    call SetUnitX(FF_E2E_kcBag, -1580.0)
    call SetUnitY(FF_E2E_kcBag, -256.0)
    call FF_E2E_KcVictimAt(-1500.0, -256.0, 1.0)
    call FF_E2E_KcBagTrace()
    call FF_E2E_After(0.5, function FF_E2E_KcBagOrder)
    call FF_E2E_After(1.0, function FF_E2E_KcWait)
endfunction

// The host's game-type dialog: "Pub Game Default", the first of the main map's four buttons.
function FF_E2E_HostClick takes nothing returns string
    return "0.5 0.478"
endfunction

function FF_E2E_Scenario takes nothing returns nothing
    local integer i = 0
    local trigger t = CreateTrigger()
    call FF_E2E_Begin("kill_credit")
    call TriggerRegisterAnyUnitEventBJ(t, EVENT_PLAYER_UNIT_DEATH)
    call TriggerAddAction(t, function FF_E2E_KcOnDeath)
    // every player gets the hero the map expects (udg_herO): created in the tavern area, like the kd scenario
    loop
        exitwhen i >= 12
        call CreateUnit(Player(i), 'H005', -2600.0, -300.0, 0.0)
        set i = i + 1
    endloop
    call FF_E2E_After(3.0, function FF_E2E_KcCase1)
    set t = null
endfunction
