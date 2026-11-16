// FF addons — Stats: per-player performance counters for the `stats,` rows of ff_result
// (written by 20-gameresult.j's flush, after the event rows; the format is docs/result-contract.md):
//   stats,<slot>,t=<mm:ss>,state=alive|out|left[,left_t=<mm:ss>],k=v,...
//   stats,<slot>,t=<mm:ss>,k=v,...
// Two rows per participant slot (1..12), both with the same t= (the bot merges them), cumulative, integers only:
// the game keeps at most 259 characters of a Preload string, and one row with every key would be ~300-350. The
// split is fixed (FF_st_Collect): with t up to 999:59, 7-digit gold sums and full-width (11-char) damage sums each
// row is at most ~230 characters.
// Keys:
//   * given/recv/mined/tech/razed/food: the score screen (GetPlayerScore), read at refresh.
//   * ukills/hkills: the map's OWN kill counters (udg_unit_kills / udg_hero_kills, kept by Trig_Multiboard_Update)
//     — the same numbers as in-game -kd and the kill log (10-killlog.j), so there is only one way kills are counted.
//     Never the score screen's kill counts: those also count illusions, own/allied and creep kills.
//   * pool_* / inh_* / koth_gold: gold the MAP moves with AdjustPlayerState (autopool, a leaver's or a dead ally's
//     gold, King of the Hill income), which the score screen never sees. Counted by one-line hooks the build inserts
//     after each of those AdjustPlayerStateBJ calls (FF_JASS_ANCHORS, scripting/jass-*/anchors.txt). The hooks are
//     plain `set`s on the arrays below: the map's trigger functions come before every addon function in the
//     script, so they can't call one. Each hook credits the real sender/receiver slot of that very call.
//   * deny_own / deny_ally: footmen and tier-1 spawns (the units a base sends) of the slot's OWN / an ALLY's base
//     killed by the slot — the team tactic of getting rid of feed units.
//   * tm_casts / tm_hits / tm_denied / tm_saves: Transmute (a projectile). A cast is a hit when the target dies to
//     the caster, denied when it dies to anyone else first (its owner or an ally killing it is the standard
//     counter — that counter is tm_saves for the slot that did it); a target still alive after FF_ST_TM_WAIT
//     seconds dodged (e.g. turned invisible).
//   * tm_creeps: the hits among tm_hits whose target was a creep hired at a creep shop (16-usage.j marks them).
//   * creeps / creep_gold: creeps hired (16-usage.j counts them; refunds excluded).
//   * atk_lvl / def_lvl / race_lvl / team_res: base attack and armor upgrade levels (Rhme / Rhar), the race
//     upgrade level (Robs / Rugf / Rhan / R004), researches done at the team's shared research building
//     (16-usage.j). Read at refresh; team copies the map hands to allies are not in team_res.
//   * dmg_out (to non-structures) / dmg_bld (to structures) / dmg_in: post-mitigation damage between
//     non-allied players (neutral creeps count as enemies), FF_STATS_DAMAGE switches it off — the only
//     per-hit cost of this file; the keys are then omitted.
//   * hero_lvl: highest hero level, a running maximum while alive (never lowered: at an elimination the map has
//     already removed the hero), frozen once the player is out or left.
// A row is rebuilt only when one of its numbers changed (FF_st_Sig): every JASS string lives until the game ends.
// All reads are synced game state; the only write is the existing local Preload of ff_result.

globals
    boolean FF_STATS_DAMAGE = true
    // Slots 1..12 (index 0 unused). The pool/inh/kothGold arrays are written by the anchor hooks.
    integer array FF_st_poolOut
    integer array FF_st_poolIn
    integer array FF_st_inhOut
    integer array FF_st_inhIn
    integer array FF_st_kothGold
    integer array FF_st_denyOwn
    integer array FF_st_denyAlly
    integer array FF_st_tmCasts
    integer array FF_st_tmHits
    integer array FF_st_tmDenied
    integer array FF_st_tmSaves
    integer array FF_st_tmCreeps
    group FF_st_hired = null
    integer array FF_st_creeps
    integer array FF_st_creepGold
    integer array FF_st_teamRes
    // Damage per slot and kind (index slot * 3 + FF_ST_DMG_*), and the fraction of a point carried between hits
    // so the integer sums don't drift.
    integer FF_ST_DMG_OUT = 0
    integer FF_ST_DMG_BLD = 1
    integer FF_ST_DMG_IN = 2
    integer array FF_st_dmg
    real array FF_st_dmgRem
    // A slot's state: alive, out (eliminated) or left while still alive.
    integer FF_ST_ALIVE = 0
    integer FF_ST_OUT = 1
    integer FF_ST_LEFT = 2
    integer array FF_st_state
    string array FF_st_leftT
    integer array FF_st_heroLvl
    // The slot's current two rows minus their `t=` and the signature of the numbers they were built from.
    string array FF_st_row
    string array FF_st_row2
    integer array FF_st_sig
    // One slot's keys and values while its rows are collected; the second row starts at FF_st_split.
    string array FF_st_key
    integer array FF_st_val
    integer FF_st_n = 0
    integer FF_st_split = 0
    // Transmutes in flight (projectile): caster, target, caster slot, expiry (game seconds). The two Transmute
    // abilities are the neutral hero's (ANtm) and the map's own copy (A0G0).
    real FF_ST_TM_WAIT = 4.0
    integer FF_ST_TM_MAX = 32
    unit array FF_st_tmCaster
    unit array FF_st_tmTarget
    integer array FF_st_tmSlot
    real array FF_st_tmUntil
    integer FF_st_tmN = 0
endglobals

function FF_st_Slot takes player p returns integer
    local integer s = GetPlayerId(p) + 1
    if s >= 1 and s <= 12 then
        return s
    endif
    return 0
endfunction

// The slot's highest hero level right now (illusions excluded); 0 without a hero.
function FF_st_HeroLevel takes integer slot returns integer
    local group g = CreateGroup()
    local unit u
    local integer best = 0
    call GroupEnumUnitsOfPlayer(g, Player(slot - 1), null)
    loop
        set u = FirstOfGroup(g)
        exitwhen u == null
        call GroupRemoveUnit(g, u)
        if IsUnitType(u, UNIT_TYPE_HERO) and not IsUnitIllusion(u) and GetHeroLevel(u) > best then
            set best = GetHeroLevel(u)
        endif
    endloop
    call DestroyGroup(g)
    set g = null
    return best
endfunction

function FF_st_Tech takes integer slot, integer techid returns integer
    return GetPlayerTechCount(Player(slot - 1), techid, true)
endfunction

function FF_st_RaceLevel takes integer slot returns integer
    return IMaxBJ(IMaxBJ(FF_st_Tech(slot, 'Robs'), FF_st_Tech(slot, 'Rugf')), IMaxBJ(FF_st_Tech(slot, 'Rhan'), FF_st_Tech(slot, 'R004')))
endfunction

// Ends the slot's alive state; its hero level is final from here on.
function FF_st_Freeze takes integer slot, integer state returns nothing
    set FF_st_heroLvl[slot] = IMaxBJ(FF_st_heroLvl[slot], FF_st_HeroLevel(slot))
    set FF_st_state[slot] = state
endfunction

// Called by the GameResult poll (1s) for every participant; true when the slot's state changed.
// A leave is checked first: the map also flips player_active off for a leaver, and that must read
// as `left`, not as an elimination.
function FF_st_Track takes integer slot, boolean active returns boolean
    if FF_st_state[slot] != FF_ST_ALIVE then
        return false
    endif
    if GetPlayerSlotState(Player(slot - 1)) == PLAYER_SLOT_STATE_LEFT then
        call FF_st_Freeze(slot, FF_ST_LEFT)
        set FF_st_leftT[slot] = FF_Elapsed()
        return true
    endif
    if not active then
        call FF_st_Freeze(slot, FF_ST_OUT)
        return true
    endif
    return false
endfunction

// Appends one key and its value to the slot being collected.
function FF_st_V takes string key, integer v returns nothing
    set FF_st_key[FF_st_n] = key
    set FF_st_val[FF_st_n] = v
    set FF_st_n = FF_st_n + 1
endfunction

// The numbers of a slot's two rows, in output order, into FF_st_key / FF_st_val: the first row holds the score
// screen, the map's own gold moves and the hero level; the second row (from FF_st_split on) the addon's counters
// and the damage.
function FF_st_Collect takes integer slot returns nothing
    local player p = Player(slot - 1)
    local integer d = slot * 3
    set FF_st_n = 0
    call FF_st_V(",given=", GetPlayerScore(p, PLAYER_SCORE_GOLD_GIVEN))
    call FF_st_V(",recv=", GetPlayerScore(p, PLAYER_SCORE_GOLD_RECEIVED))
    call FF_st_V(",pool_out=", FF_st_poolOut[slot])
    call FF_st_V(",pool_in=", FF_st_poolIn[slot])
    call FF_st_V(",inh_out=", FF_st_inhOut[slot])
    call FF_st_V(",inh_in=", FF_st_inhIn[slot])
    call FF_st_V(",mined=", GetPlayerScore(p, PLAYER_SCORE_GOLD_MINED_TOTAL))
    call FF_st_V(",tech=", GetPlayerScore(p, PLAYER_SCORE_TECH_PERCENT))
    call FF_st_V(",ukills=", udg_unit_kills[slot])
    call FF_st_V(",hkills=", udg_hero_kills[slot])
    call FF_st_V(",razed=", GetPlayerScore(p, PLAYER_SCORE_STRUCT_RAZED))
    call FF_st_V(",food=", GetPlayerScore(p, PLAYER_SCORE_FOOD_MAXUSED))
    call FF_st_V(",koth_gold=", FF_st_kothGold[slot])
    call FF_st_V(",hero_lvl=", FF_st_heroLvl[slot])
    set FF_st_split = FF_st_n
    call FF_st_V(",deny_own=", FF_st_denyOwn[slot])
    call FF_st_V(",deny_ally=", FF_st_denyAlly[slot])
    call FF_st_V(",tm_casts=", FF_st_tmCasts[slot])
    call FF_st_V(",tm_hits=", FF_st_tmHits[slot])
    call FF_st_V(",tm_creeps=", FF_st_tmCreeps[slot])
    call FF_st_V(",tm_denied=", FF_st_tmDenied[slot])
    call FF_st_V(",tm_saves=", FF_st_tmSaves[slot])
    call FF_st_V(",creeps=", FF_st_creeps[slot])
    call FF_st_V(",creep_gold=", FF_st_creepGold[slot])
    call FF_st_V(",atk_lvl=", FF_st_Tech(slot, 'Rhme'))
    call FF_st_V(",def_lvl=", FF_st_Tech(slot, 'Rhar'))
    call FF_st_V(",race_lvl=", FF_st_RaceLevel(slot))
    call FF_st_V(",team_res=", FF_st_teamRes[slot])
    if FF_STATS_DAMAGE then
        call FF_st_V(",dmg_out=", FF_st_dmg[d + FF_ST_DMG_OUT])
        call FF_st_V(",dmg_bld=", FF_st_dmg[d + FF_ST_DMG_BLD])
        call FF_st_V(",dmg_in=", FF_st_dmg[d + FF_ST_DMG_IN])
    endif
    set p = null
endfunction

// A hash over the slot's state and the collected numbers (integer overflow wraps), so an unchanged row is
// detected without building its string.
function FF_st_Sig takes integer slot returns integer
    local integer h = FF_st_state[slot]
    local integer i = 0
    loop
        exitwhen i >= FF_st_n
        set h = h * 31 + FF_st_val[i]
        set i = i + 1
    endloop
    return h
endfunction

// The collected keys from..to-1, each as ,<key>=<value>.
function FF_st_Join takes integer from, integer to returns string
    local string s = ""
    local integer i = from
    loop
        exitwhen i >= to
        set s = s + FF_st_key[i] + I2S(FF_st_val[i])
        set i = i + 1
    endloop
    return s
endfunction

function FF_st_StateField takes integer slot returns string
    if FF_st_state[slot] == FF_ST_ALIVE then
        return ",state=alive"
    elseif FF_st_state[slot] == FF_ST_OUT then
        return ",state=out"
    endif
    return ",state=left,left_t=" + FF_st_leftT[slot]
endfunction

// Rebuilds the slot's two rows if one of their numbers changed; true if they did.
function FF_st_Refresh takes integer slot returns boolean
    local integer sig
    if FF_st_state[slot] == FF_ST_ALIVE then
        set FF_st_heroLvl[slot] = IMaxBJ(FF_st_heroLvl[slot], FF_st_HeroLevel(slot))
    endif
    call FF_st_Collect(slot)
    set sig = FF_st_Sig(slot)
    if FF_st_row[slot] != null and sig == FF_st_sig[slot] then
        return false
    endif
    set FF_st_sig[slot] = sig
    set FF_st_row[slot] = FF_st_StateField(slot) + FF_st_Join(0, FF_st_split)
    set FF_st_row2[slot] = FF_st_Join(FF_st_split, FF_st_n)
    return true
endfunction

// The units a base sends that count for denies: footmen (tier 0) and the tier-1 spawns (spawns.csv).
function FF_st_IsFeedUnit takes integer id returns boolean
    return id == 'hfoo' or id == 'earc' or id == 'hrif' or id == 'uban' or id == 'otbk' or id == 'nskf' or id == 'ugho'
endfunction

// Removes Transmute i from the in-flight list (the last one takes its place).
function FF_st_TmDrop takes integer i returns nothing
    set FF_st_tmN = FF_st_tmN - 1
    set FF_st_tmCaster[i] = FF_st_tmCaster[FF_st_tmN]
    set FF_st_tmTarget[i] = FF_st_tmTarget[FF_st_tmN]
    set FF_st_tmSlot[i] = FF_st_tmSlot[FF_st_tmN]
    set FF_st_tmUntil[i] = FF_st_tmUntil[FF_st_tmN]
    set FF_st_tmCaster[FF_st_tmN] = null
    set FF_st_tmTarget[FF_st_tmN] = null
endfunction

// Called every second by the usage poll: a Transmute whose target is still alive after the wait was dodged.
function FF_st_TmExpire takes nothing returns nothing
    local real now = TimerGetElapsed(FF_gameTimer)
    local integer i = FF_st_tmN - 1
    loop
        exitwhen i < 0
        if now > FF_st_tmUntil[i] then
            call FF_st_TmDrop(i)
        endif
        set i = i - 1
    endloop
endfunction

// A Transmute cast on a unit: counted, and followed until its target dies or the wait runs out.
function FF_st_OnSpell takes nothing returns nothing
    local integer id = GetSpellAbilityId()
    local integer s
    if (id == 'ANtm' or id == 'A0G0') and FF_st_tmN < FF_ST_TM_MAX then
        set s = FF_st_Slot(GetOwningPlayer(GetTriggerUnit()))
        if s > 0 and GetSpellTargetUnit() != null then
            set FF_st_tmCasts[s] = FF_st_tmCasts[s] + 1
            set FF_st_tmCaster[FF_st_tmN] = GetTriggerUnit()
            set FF_st_tmTarget[FF_st_tmN] = GetSpellTargetUnit()
            set FF_st_tmSlot[FF_st_tmN] = s
            set FF_st_tmUntil[FF_st_tmN] = TimerGetElapsed(FF_gameTimer) + FF_ST_TM_WAIT
            set FF_st_tmN = FF_st_tmN + 1
        endif
    endif
endfunction

// A unit died: resolves a Transmute in flight on it, and counts a deny.
function FF_st_OnDeath takes nothing returns nothing
    local unit victim = GetTriggerUnit()
    local unit killer = GetKillingUnit()
    local player vp = GetOwningPlayer(victim)
    local player kp = null
    local integer ks = 0
    local integer i = FF_st_tmN - 1
    if killer != null then
        set kp = GetOwningPlayer(killer)
        set ks = FF_st_Slot(kp)
    endif
    // Transmute in flight on this unit: hit, or denied (and saved, if its own side killed it).
    loop
        exitwhen i < 0
        if FF_st_tmTarget[i] == victim then
            if killer != null and killer == FF_st_tmCaster[i] then
                set FF_st_tmHits[FF_st_tmSlot[i]] = FF_st_tmHits[FF_st_tmSlot[i]] + 1
                if IsUnitInGroup(victim, FF_st_hired) then
                    set FF_st_tmCreeps[FF_st_tmSlot[i]] = FF_st_tmCreeps[FF_st_tmSlot[i]] + 1
                endif
            else
                set FF_st_tmDenied[FF_st_tmSlot[i]] = FF_st_tmDenied[FF_st_tmSlot[i]] + 1
                if ks > 0 and (kp == vp or IsPlayerAlly(kp, vp)) then
                    set FF_st_tmSaves[ks] = FF_st_tmSaves[ks] + 1
                endif
            endif
            call FF_st_TmDrop(i)
        endif
        set i = i - 1
    endloop
    call GroupRemoveUnit(FF_st_hired, victim)
    // Denies: a feed unit of the killer's own or an allied base.
    if ks > 0 and FF_st_IsFeedUnit(GetUnitTypeId(victim)) and not IsUnitIllusion(victim) then
        if kp == vp then
            set FF_st_denyOwn[ks] = FF_st_denyOwn[ks] + 1
        elseif IsPlayerAlly(kp, vp) then
            set FF_st_denyAlly[ks] = FF_st_denyAlly[ks] + 1
        endif
    endif
    set victim = null
    set killer = null
    set vp = null
    set kp = null
endfunction

// Adds d points of damage of one kind to the slot's sum.
function FF_st_AddDamage takes integer slot, integer kind, real d returns nothing
    local integer i = slot * 3 + kind
    local real r = FF_st_dmgRem[i] + d
    set FF_st_dmg[i] = FF_st_dmg[i] + R2I(r)
    set FF_st_dmgRem[i] = r - I2R(R2I(r))
endfunction

// Damage between non-allied players. Condition-only (no action thread per hit); always returns false.
function FF_st_OnDamage takes nothing returns boolean
    local unit src = GetEventDamageSource()
    local unit tgt = GetTriggerUnit()
    local real d = GetEventDamage()
    local player ps
    local player pt
    local integer s
    local integer t
    if src != null and d > 0.0 then
        set ps = GetOwningPlayer(src)
        set pt = GetOwningPlayer(tgt)
        if ps != pt and not IsPlayerAlly(ps, pt) then
            set s = GetPlayerId(ps) + 1
            set t = GetPlayerId(pt) + 1
            if s <= 12 then
                if IsUnitType(tgt, UNIT_TYPE_STRUCTURE) then
                    call FF_st_AddDamage(s, FF_ST_DMG_BLD, d)
                else
                    call FF_st_AddDamage(s, FF_ST_DMG_OUT, d)
                endif
            endif
            if t <= 12 then
                call FF_st_AddDamage(t, FF_ST_DMG_IN, d)
            endif
        endif
        set ps = null
        set pt = null
    endif
    set src = null
    set tgt = null
    return false
endfunction

function FF_Stats_Init takes nothing returns nothing
    local trigger t = CreateTrigger()
    call TriggerRegisterAnyUnitEventBJ(t, EVENT_PLAYER_UNIT_SPELL_EFFECT)
    call TriggerAddAction(t, function FF_st_OnSpell)
    set t = CreateTrigger()
    call TriggerRegisterAnyUnitEventBJ(t, EVENT_PLAYER_UNIT_DEATH)
    call TriggerAddAction(t, function FF_st_OnDeath)
    if FF_STATS_DAMAGE then
        set t = CreateTrigger()
        call TriggerRegisterAnyUnitEventBJ(t, EVENT_PLAYER_UNIT_DAMAGED)
        call TriggerAddCondition(t, Condition(function FF_st_OnDamage))
    endif
    set t = null
endfunction
