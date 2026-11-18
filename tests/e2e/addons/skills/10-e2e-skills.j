// e2e scenario "skills" (main and Solo): every hero skill of the map, at every level, in the real client. The data
// (05-e2e-skills-data.j) is generated at build time by tests/e2e/gen_skills.py from the map's own object data (with
// the WC3 3.0 level fill and the map fixes): the cells the map stores and each skill's base order. The client is
// player 1 (slot 1); the other seats are computers.
//   readback  per skill: a caster of the skill's hero type gets it (UnitAddAbility); the engine's level count is
//             recorded where it differs from the map's (`lv,<abil>,map=..,engine=..`: a skill without `alev` keeps its
//             base ability's count, cells above it are dead data), and at each level every stored
//             numeric cell is read back from the engine (BlzGetAbility{Integer,Real,Boolean}LevelField). Only
//             differences are recorded: `rb,<abil>,<field>,<level>,got=..,want=..`, then `readback,cells=..,bad=..`.
//   casts     per skill and level, SK_SLOTS at a time at spots around the map centre: a fresh caster (invulnerable,
//             100000 mana, no cooldown) gets the skill at that level and its base order is tried as an instant,
//             on an enemy unit, on an allied unit, at a point, as an instant — the first the unit then carries out. Recorded per cast:
//             `c,<abil>,<level>,how=i|e|a|p|-,eff=<0/1>,mana=<spent>,cd=<cooldown started, x100>`; the checker
//             compares mana / cooldown with the map's amcs / acdn (skills_expect.json).
// Rows are added without a flush (FF_SK_Add) and flushed every 40: ~1500 rows.

globals
    constant integer SK_SLOTS = 8
    integer FF_SK_chunk = 0
    integer FF_SK_ai = 0
    integer FF_SK_bad = 0
    integer FF_SK_read = 0
    integer FF_SK_rows = 0
    // the cast queue: ability index + level, the next one to hand out
    integer FF_SK_qa = 0
    integer FF_SK_ql = 1
    // per slot
    unit array FF_SK_caster
    unit array FF_SK_enemy
    unit array FF_SK_ally
    unit array FF_SK_own
    unit array FF_SK_hero
    boolean array FF_SK_retry
    integer array FF_SK_slotA
    integer array FF_SK_abil
    integer array FF_SK_lvl
    integer array FF_SK_eff
    integer array FF_SK_mana
    integer array FF_SK_cd
    string array FF_SK_how
    real array FF_SK_x
    real array FF_SK_y
    trigger FF_SK_effTrig = null
    timer array FF_SK_measTimer
    integer FF_SK_casts = 0
    // the level count the engine gives each skill (a skill without `alev` keeps its base ability's count, and cells
    // the map stores above it are never used)
    integer array FF_SK_aEng
    integer FF_SK_dead = 0
endglobals

function FF_SK_Add takes string row returns nothing
    set FF_E2E_rows[FF_E2E_n] = row
    set FF_E2E_n = FF_E2E_n + 1
    set FF_SK_rows = FF_SK_rows + 1
    if FF_SK_rows >= 40 then
        set FF_SK_rows = 0
        call FF_E2E_Flush()
    endif
endfunction

function FF_SK_R2S100 takes real r returns string
    return I2S(R2I(r * 100.0 + 0.5))
endfunction

// --- casts -------------------------------------------------------------------------------------------------------

function FF_SK_Measure takes nothing returns nothing
    local integer k = 0
    loop
        exitwhen k >= SK_SLOTS
        if GetExpiredTimer() == FF_SK_measTimer[k] and FF_SK_caster[k] != null then
            set FF_SK_mana[k] = R2I(100000.0 - GetUnitState(FF_SK_caster[k], UNIT_STATE_MANA) + 0.5)
            set FF_SK_cd[k] = R2I(BlzGetUnitAbilityCooldownRemaining(FF_SK_caster[k], FF_SK_abil[k]) * 100.0 + 0.5)
        endif
        set k = k + 1
    endloop
endfunction

function FF_SK_OnEffect takes nothing returns nothing
    local unit u = GetTriggerUnit()
    local integer k = 0
    loop
        exitwhen k >= SK_SLOTS
        if u == FF_SK_caster[k] and GetSpellAbilityId() == FF_SK_abil[k] and FF_SK_eff[k] == 0 then
            // the engine takes the mana and starts the cooldown after this event (measured: both read 0 here)
            set FF_SK_eff[k] = 1
            call TimerStart(FF_SK_measTimer[k], 0.0, false, function FF_SK_Measure)
        endif
        set k = k + 1
    endloop
    set u = null
endfunction

function FF_SK_Clean takes integer k returns nothing
    if FF_SK_caster[k] != null then
        call RemoveUnit(FF_SK_caster[k])
        set FF_SK_caster[k] = null
    endif
    if FF_SK_enemy[k] != null then
        call RemoveUnit(FF_SK_enemy[k])
        set FF_SK_enemy[k] = null
    endif
    if FF_SK_ally[k] != null then
        call RemoveUnit(FF_SK_ally[k])
        set FF_SK_ally[k] = null
    endif
    if FF_SK_own[k] != null then
        call RemoveUnit(FF_SK_own[k])
        set FF_SK_own[k] = null
    endif
    if FF_SK_hero[k] != null then
        call RemoveUnit(FF_SK_hero[k])
        set FF_SK_hero[k] = null
    endif
endfunction

function FF_SK_Target takes player p, real x, real y returns unit
    local unit u = CreateUnit(p, 'hfoo', x, y, 0.0)
    call BlzSetUnitMaxHP(u, 1000000)
    call SetUnitState(u, UNIT_STATE_LIFE, 1000000.0)
    call IssueImmediateOrder(u, "holdposition")
    return u
endfunction

// Clears what a refused attempt left (a move toward a target, ...) before the next one; always true.
function FF_SK_Stop takes unit c returns boolean
    call IssueImmediateOrder(c, "stop")
    return true
endfunction

// Casts slot k's skill (FF_SK_slotA / FF_SK_lvl) with fresh units; `dy` moves the spot (a retry tries elsewhere).
function FF_SK_Cast takes integer k, real dy returns nothing
    local integer i = FF_SK_slotA[k]
    local integer id = FF_SK_abil[k]
    local string o
    local unit c
    local real x = FF_SK_x[k]
    local real y = FF_SK_y[k] + dy
    set FF_SK_eff[k] = 0
    set FF_SK_mana[k] = -1
    set FF_SK_cd[k] = -1
    set o = FF_SK_aOrder[i]
    if o == "" or o == null then
        set o = FF_SK_aOrderOn[i]
    endif
    set c = CreateUnit(Player(0), FF_SK_aHero[i], x, y, 0.0)
    set FF_SK_caster[k] = c
    call SetUnitInvulnerable(c, true)
    call BlzSetUnitMaxMana(c, 100000)
    call SetUnitState(c, UNIT_STATE_MANA, 100000.0)
    if GetUnitAbilityLevel(c, id) == 0 then
        call UnitAddAbility(c, id)
    endif
    call SetUnitAbilityLevel(c, id, FF_SK_lvl[k])
    call BlzEndUnitAbilityCooldown(c, id)
    set FF_SK_enemy[k] = FF_SK_Target(Player(3), x + 250.0, y)
    // an enemy hero with mana, for spells that take only heroes (Finger of Death) or mana (Mana Burn)
    set FF_SK_hero[k] = CreateUnit(Player(3), 'Hpal', x + 250.0, y + 200.0, 0.0)
    call SetUnitState(FF_SK_hero[k], UNIT_STATE_MANA, GetUnitState(FF_SK_hero[k], UNIT_STATE_MAX_MANA))
    call IssueImmediateOrder(FF_SK_hero[k], "holdposition")
    // friendly targets at half life (healing spells refuse a full-health target); the own unit for spells that
    // take only the caster's own non-heroes (Dark Ritual, Death Pact)
    set FF_SK_ally[k] = FF_SK_Target(Player(1), x - 250.0, y)
    call SetUnitState(FF_SK_ally[k], UNIT_STATE_LIFE, 500000.0)
    set FF_SK_own[k] = FF_SK_Target(Player(0), x, y - 250.0)
    call SetUnitState(FF_SK_own[k], UNIT_STATE_LIFE, 500000.0)
    // an order counts once the unit carries it (or its spell already went off): the engine also "accepts" an
    // instant order for a targeted spell and then does nothing (measured)
    set FF_SK_how[k] = "x"
    if o == "" or o == null then
        set FF_SK_how[k] = "-"
    elseif IssueTargetOrder(c, o, FF_SK_enemy[k]) and (GetUnitCurrentOrder(c) == OrderId(o) or FF_SK_eff[k] == 1) then
        set FF_SK_how[k] = "e"
    elseif FF_SK_Stop(c) and IssueTargetOrder(c, o, FF_SK_hero[k]) and (GetUnitCurrentOrder(c) == OrderId(o) or FF_SK_eff[k] == 1) then
        set FF_SK_how[k] = "h"
    elseif FF_SK_Stop(c) and IssueTargetOrder(c, o, FF_SK_ally[k]) and (GetUnitCurrentOrder(c) == OrderId(o) or FF_SK_eff[k] == 1) then
        set FF_SK_how[k] = "a"
    elseif FF_SK_Stop(c) and IssueTargetOrder(c, o, FF_SK_own[k]) and (GetUnitCurrentOrder(c) == OrderId(o) or FF_SK_eff[k] == 1) then
        set FF_SK_how[k] = "o"
    elseif FF_SK_Stop(c) and IssuePointOrder(c, o, x + 300.0, y) and (GetUnitCurrentOrder(c) == OrderId(o) or FF_SK_eff[k] == 1) then
        set FF_SK_how[k] = "p"
    elseif FF_SK_Stop(c) and IssueImmediateOrder(c, o) and (GetUnitCurrentOrder(c) == OrderId(o) or FF_SK_eff[k] == 1) then
        set FF_SK_how[k] = "i"
    endif
    set FF_SK_casts = FF_SK_casts + 1
    set c = null
endfunction

// Starts the next queued cast in slot k; false when the queue is done.
function FF_SK_Start takes integer k returns boolean
    loop
        if FF_SK_qa >= FF_SK_n then
            return false
        endif
        exitwhen FF_SK_ql <= IMinBJ(FF_SK_aLevels[FF_SK_qa], FF_SK_aEng[FF_SK_qa])
        set FF_SK_qa = FF_SK_qa + 1
        set FF_SK_ql = 1
    endloop
    set FF_SK_slotA[k] = FF_SK_qa
    set FF_SK_abil[k] = FF_SK_aId[FF_SK_qa]
    set FF_SK_lvl[k] = FF_SK_ql
    set FF_SK_ql = FF_SK_ql + 1
    set FF_SK_retry[k] = false
    call FF_SK_Cast(k, 0.0)
    return true
endfunction

function FF_SK_Finish takes nothing returns nothing
    call FF_SK_Add("casts,n=" + I2S(FF_SK_casts) + ",t=" + I2S(FF_E2E_Now()))
    call FF_E2E_Done()
endfunction

// Every 2.5 s: record the slots' casts, clean up, start the next ones.
function FF_SK_Round takes nothing returns nothing
    local integer k = 0
    local boolean any = false
    loop
        exitwhen k >= SK_SLOTS
        if FF_SK_caster[k] != null and FF_SK_eff[k] == 0 and FF_SK_how[k] != "-" and not FF_SK_retry[k] then
            // no effect (or refused): once more, 300 further on, with fresh units
            call FF_SK_Clean(k)
            set FF_SK_retry[k] = true
            call FF_SK_Cast(k, 300.0)
            set any = true
        else
            if FF_SK_caster[k] != null then
                call FF_SK_Add("c," + FF_us_Id2S(FF_SK_abil[k]) + "," + I2S(FF_SK_lvl[k]) + ",how=" + FF_SK_how[k] + ",eff=" + I2S(FF_SK_eff[k]) + ",mana=" + I2S(FF_SK_mana[k]) + ",cd=" + I2S(FF_SK_cd[k]) + ",retry=" + FF_E2E_Bool(FF_SK_retry[k]))
                call FF_SK_Clean(k)
            endif
            if FF_SK_Start(k) then
                set any = true
            endif
        endif
        set k = k + 1
    endloop
    if any then
        call TimerStart(GetExpiredTimer(), 2.5, false, function FF_SK_Round)
    else
        call DestroyTimer(GetExpiredTimer())
        call FF_SK_Finish()
    endif
endfunction

function FF_SK_Casts takes nothing returns nothing
    local integer k = 0
    local real a
    if FF_E2E_Now() < FF_SK_CastAfter() then
        call FF_E2E_After(2.0, function FF_SK_Casts)
        return
    endif
    loop
        exitwhen k >= SK_SLOTS
        set FF_SK_measTimer[k] = CreateTimer()
        set k = k + 1
    endloop
    set k = 0
    set FF_SK_effTrig = CreateTrigger()
    call TriggerRegisterAnyUnitEventBJ(FF_SK_effTrig, EVENT_PLAYER_UNIT_SPELL_EFFECT)
    call TriggerAddAction(FF_SK_effTrig, function FF_SK_OnEffect)
    // spots on a ring around the map centre, ~1150 apart
    loop
        exitwhen k >= SK_SLOTS
        set a = 2.0 * bj_PI * k / SK_SLOTS
        set FF_SK_x[k] = 1500.0 * Cos(a)
        set FF_SK_y[k] = 1500.0 * Sin(a)
        set k = k + 1
    endloop
    call FF_SK_Add("casts,start=" + I2S(FF_E2E_Now()) + ",slots=" + I2S(SK_SLOTS))
    set FF_SK_qa = 0
    set FF_SK_ql = 1
    call TimerStart(CreateTimer(), 0.1, false, function FF_SK_Round)
endfunction

// --- readback ----------------------------------------------------------------------------------------------------

function FF_SK_ReadOne takes nothing returns nothing
    local integer i = FF_SK_ai
    local integer id
    local unit u
    local ability ab
    local integer j
    local integer l
    local integer got
    local real gr
    if i >= FF_SK_n then
        call DestroyTimer(GetExpiredTimer())
        call FF_SK_Add("readback,skills=" + I2S(FF_SK_n) + ",cells=" + I2S(FF_SK_read) + ",bad=" + I2S(FF_SK_bad) + ",dead=" + I2S(FF_SK_dead) + ",t=" + I2S(FF_E2E_Now()))
        call FF_E2E_Flush()
        call FF_SK_Casts()
        return
    endif
    set id = FF_SK_aId[i]
    set u = CreateUnit(Player(0), FF_SK_aHero[i], 0.0, 0.0, 0.0)
    call SetUnitInvulnerable(u, true)
    if GetUnitAbilityLevel(u, id) == 0 then
        call UnitAddAbility(u, id)
    endif
    set ab = BlzGetUnitAbility(u, id)
    if ab == null then
        call FF_SK_Add("rb," + FF_us_Id2S(id) + ",noability,hero=" + FF_us_Id2S(FF_SK_aHero[i]))
        set FF_SK_bad = FF_SK_bad + 1
        set FF_SK_aEng[i] = 0
    else
        set FF_SK_aEng[i] = BlzGetAbilityIntegerField(ab, ABILITY_IF_LEVELS)
        if FF_SK_aEng[i] != FF_SK_aLevels[i] then
            call FF_SK_Add("lv," + FF_us_Id2S(id) + ",map=" + I2S(FF_SK_aLevels[i]) + ",engine=" + I2S(FF_SK_aEng[i]))
        endif
        set j = FF_SK_aCell0[i]
        loop
            exitwhen j >= FF_SK_aCellN[i]
            set l = FF_SK_cLevel[j] - 1
            if l >= FF_SK_aEng[i] then
                set FF_SK_dead = FF_SK_dead + 1
                set j = j + 1
            else
            set FF_SK_read = FF_SK_read + 1
            if FF_SK_cReal[j] then
                set gr = BlzGetAbilityRealLevelField(ab, ConvertAbilityRealLevelField(FF_SK_cField[j]), l)
                if RAbsBJ(gr - FF_SK_cRealV[j]) > 0.001 + 0.0001 * RAbsBJ(FF_SK_cRealV[j]) then
                    set FF_SK_bad = FF_SK_bad + 1
                    call FF_SK_Add("rb," + FF_us_Id2S(id) + "," + FF_us_Id2S(FF_SK_cField[j]) + "," + I2S(l + 1) + ",got=" + R2S(gr) + ",want=" + R2S(FF_SK_cRealV[j]))
                endif
            else
                set got = BlzGetAbilityIntegerLevelField(ab, ConvertAbilityIntegerLevelField(FF_SK_cField[j]), l)
                if got != FF_SK_cInt[j] and (FF_SK_cInt[j] == 0 or FF_SK_cInt[j] == 1) then
                    // a flag stored as an integer: the engine may only answer the boolean read
                    if BlzGetAbilityBooleanLevelField(ab, ConvertAbilityBooleanLevelField(FF_SK_cField[j]), l) == (FF_SK_cInt[j] == 1) then
                        set got = FF_SK_cInt[j]
                    endif
                endif
                if got != FF_SK_cInt[j] then
                    set FF_SK_bad = FF_SK_bad + 1
                    call FF_SK_Add("rb," + FF_us_Id2S(id) + "," + FF_us_Id2S(FF_SK_cField[j]) + "," + I2S(l + 1) + ",got=" + I2S(got) + ",want=" + I2S(FF_SK_cInt[j]))
                endif
            endif
            set j = j + 1
            endif
        endloop
    endif
    call RemoveUnit(u)
    set FF_SK_ai = i + 1
    call TimerStart(GetExpiredTimer(), 0.02, false, function FF_SK_ReadOne)
    set u = null
    set ab = null
endfunction

function FF_SK_LoadNext takes nothing returns nothing
    if FF_SK_chunk < FF_SK_Chunks() then
        call FF_SK_LoadChunk(FF_SK_chunk)
        set FF_SK_chunk = FF_SK_chunk + 1
        call TimerStart(GetExpiredTimer(), 0.01, false, function FF_SK_LoadNext)
        return
    endif
    call FF_SK_Add("data,skills=" + I2S(FF_SK_n) + ",cells=" + I2S(FF_SK_c))
    set FF_SK_ai = 0
    call TimerStart(GetExpiredTimer(), 0.05, false, function FF_SK_ReadOne)
endfunction

function FF_E2E_Scenario takes nothing returns nothing
    call FF_E2E_Row("e2e,scenario=skills,local=" + I2S(GetPlayerId(GetLocalPlayer())) + ",bot=" + FF_E2E_Bool(FF_LocalClientIsBot()))
    // a hero for the client (the map's tavern-area pick), or the AFK kick removes it after the mass
    call CreateUnit(Player(0), 'H005', -2600.0, -300.0, 0.0)
    call FF_E2E_Active()
    call TimerStart(CreateTimer(), 0.01, false, function FF_SK_LoadNext)
endfunction
