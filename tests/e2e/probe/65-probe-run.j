// FF 3.0 probe v6 — Blizzard vs buildings with the map fix (data/object_overrides.csv: Hbz4 = 0). See 55-probe-core.j.
//
// v1-v5 (2026-09-15) found and confirmed the WC3 3.0 fixes in the level fill. v6 checks the owner's balance change on the
// maps as they would ship: Blizzard L1/L4/L6 must not damage an enemy scout tower, and L2/L5/L6 still damage every other
// target kind (ground, air, mechanical, hero, own units). Writes CustomMapData\ff_probe.txt.

globals
    player FF_PB_p = null
    player FF_PB_e = null
    real FF_PB_cx = 0.0
    real FF_PB_cy = 0.0
    group FF_PB_g = null
    unit array FF_PB_lane
    real array FF_PB_laneVal
    real array FF_PB_base
    string array FF_PB_sum
    integer FF_PB_sumN = 0
endglobals

function FF_PB_Say takes string s returns nothing
    call DisplayTimedTextToPlayer(GetLocalPlayer(), 0, 0, 600.0, s)
endfunction

function FF_PB_LaneX takes integer lane returns real
    return FF_PB_cx - 1200.0 + I2R(ModuloInteger(lane - 1, 3)) * 1200.0
endfunction

function FF_PB_LaneY takes integer lane returns real
    if lane <= 3 then
        return FF_PB_cy + 700.0
    endif
    return FF_PB_cy - 700.0
endfunction

function FF_PB_Track takes unit u returns unit
    call GroupAddUnit(FF_PB_g, u)
    return u
endfunction

function FF_PB_Cleanup takes nothing returns nothing
    local unit u
    loop
        set u = FirstOfGroup(FF_PB_g)
        exitwhen u == null
        call GroupRemoveUnit(FF_PB_g, u)
        call RemoveUnit(u)
    endloop
endfunction

// Enemy test footman: 10000 HP, no attack, no creep AI.
function FF_PB_Enemy takes real x, real y, boolean paused returns unit
    local unit u = FF_PB_Track(CreateUnit(FF_PB_e, 'hfoo', x, y, 0.0))
    call BlzSetUnitMaxHP(u, 10000)
    call SetWidgetLife(u, 10000.0)
    call UnitRemoveAbility(u, 'Aatk')
    call RemoveGuardPosition(u)
    call UnitAddSleepPerm(u, false)
    call PauseUnit(u, paused)
    return u
endfunction

function FF_PB_EnemyRingP takes integer lane, real x, real y, boolean paused returns nothing
    local integer k = 0
    loop
        exitwhen k >= 5
        set FF_PB_lane[lane * 8 + k] = FF_PB_Enemy(x + 120.0 * Cos(I2R(k) * 1.2566), y + 120.0 * Sin(I2R(k) * 1.2566), paused)
        if not paused then
            call IssueImmediateOrder(FF_PB_lane[lane * 8 + k], "holdposition")
        endif
        set k = k + 1
    endloop
endfunction

function FF_PB_EnemyRing takes integer lane, real x, real y returns nothing
    call FF_PB_EnemyRingP(lane, x, y, true)
endfunction

function FF_PB_LostHP takes integer lane returns real
    local integer k = 0
    local real sum = 0.0
    loop
        exitwhen k >= 5
        set sum = sum + (10000.0 - GetWidgetLife(FF_PB_lane[lane * 8 + k]))
        set k = k + 1
    endloop
    return sum
endfunction

function FF_PB_ReadReal takes unit u, integer abil, integer field, integer level returns string
    local ability ab = BlzGetUnitAbility(u, abil)
    if ab == null then
        return "noability"
    endif
    return FF_PB_R(BlzGetAbilityRealLevelField(ab, ConvertAbilityRealLevelField(field), level - 1))
endfunction

function FF_PB_ReadInt takes unit u, integer abil, integer field, integer level returns string
    local ability ab = BlzGetUnitAbility(u, abil)
    if ab == null then
        return "noability"
    endif
    return I2S(BlzGetAbilityIntegerLevelField(ab, ConvertAbilityIntegerLevelField(field), level - 1))
endfunction

function FF_PB_ReadStr takes unit u, integer abil, integer field, integer level returns string
    local ability ab = BlzGetUnitAbility(u, abil)
    local string a
    local string b
    if ab == null then
        return "noability"
    endif
    set a = BlzGetAbilityStringLevelField(ab, ConvertAbilityStringLevelField(field), level - 1)
    set b = BlzGetAbilityStringLevelArrayField(ab, ConvertAbilityStringLevelArrayField(field), level - 1, 0)
    if a == null then
        set a = "null"
    endif
    if b == null then
        set b = "null"
    endif
    return a + "/" + b
endfunction

// ---------------------------------------------------------------------------------------------- finish
function FF_PB_Finish takes nothing returns nothing
    local integer c = 0
    local integer i
    local string array cname
    set cname[0] = "CTRL_X"
    set cname[1] = "CTRL_S"
    set cname[2] = "NEG"
    set cname[3] = "BELOW"
    set cname[4] = "ABOVE"
    set cname[5] = "FILL"
    set cname[6] = "GAP"
    call DestroyTimer(GetExpiredTimer())
    call PreloadGenClear()
    call PreloadGenStart()
    call Preload("FF 3.0 probe v6 | " + I2S(FF_PB_n) + " cells | results: ok zero default other unreadable noability")
    loop
        exitwhen c > 6
        set i = c * 8
        set FF_PB_sum[FF_PB_sumN] = "S " + cname[c] + " ok=" + I2S(FF_PB_cnt[i]) + " zero=" + I2S(FF_PB_cnt[i + 1]) + " default=" + I2S(FF_PB_cnt[i + 2]) + " other=" + I2S(FF_PB_cnt[i + 3]) + " unreadable=" + I2S(FF_PB_cnt[i + 4]) + " noabil=" + I2S(FF_PB_cnt[i + 5])
        call Preload(FF_PB_sum[FF_PB_sumN])
        call FF_PB_Say(FF_PB_sum[FF_PB_sumN])
        set FF_PB_sumN = FF_PB_sumN + 1
        set c = c + 1
    endloop
    set i = 0
    loop
        exitwhen i >= FF_PB_outN
        call Preload(FF_PB_out[i])
        if SubString(FF_PB_out[i], 0, 2) != "R " then
            call FF_PB_Say(FF_PB_out[i])
        endif
        set i = i + 1
    endloop
    call Preload("END")
    call PreloadGenEnd(FF_DataFile("ff_probe"))
    call FF_PB_Say("|cff00ff00PROBE DONE|r - results saved to Documents\\Warcraft III\\CustomMapData\\ff_probe.txt")
endfunction

// ---------------------------------------------------------------------------------------------- BZ: Blizzard default targets + token variants
// Ring kinds: 0 mixed = enemy footman, enemy gryphon (air), enemy steam tank (mechanical), enemy paladin (hero), OWN
// footman | 1 structure = enemy scout tower + 4 enemy footmen | 2 plain = 5 enemy footmen. All paused, 10000 HP, no attack.
function FF_PB_RingUnit takes integer lane, integer k, player owner, integer unitId, real x, real y returns nothing
    local unit u = FF_PB_Track(CreateUnit(owner, unitId, x, y, 0.0))
    call BlzSetUnitMaxHP(u, 10000)
    call SetWidgetLife(u, 10000.0)
    call UnitRemoveAbility(u, 'Aatk')
    call RemoveGuardPosition(u)
    call UnitAddSleepPerm(u, false)
    call PauseUnit(u, true)
    set FF_PB_lane[lane * 8 + k] = u
endfunction

function FF_PB_Ring takes integer lane, integer kind, real x, real y returns nothing
    local integer k = 0
    local real a
    if kind == 2 then
        call FF_PB_EnemyRing(lane, x, y)
        return
    endif
    loop
        exitwhen k >= 5
        set a = I2R(k) * 1.2566
        if kind == 1 and k == 0 then
            call FF_PB_RingUnit(lane, 0, FF_PB_e, 'hwtw', x, y)
        elseif kind == 1 then
            call FF_PB_RingUnit(lane, k, FF_PB_e, 'hfoo', x + 190.0 * Cos(a), y + 190.0 * Sin(a))
        elseif k == 0 then
            call FF_PB_RingUnit(lane, 0, FF_PB_e, 'hfoo', x + 120.0 * Cos(a), y + 120.0 * Sin(a))
        elseif k == 1 then
            call FF_PB_RingUnit(lane, 1, FF_PB_e, 'hgry', x + 120.0 * Cos(a), y + 120.0 * Sin(a))
        elseif k == 2 then
            call FF_PB_RingUnit(lane, 2, FF_PB_e, 'hmtt', x + 120.0 * Cos(a), y + 120.0 * Sin(a))
        elseif k == 3 then
            call FF_PB_RingUnit(lane, 3, FF_PB_e, 'Hpal', x + 120.0 * Cos(a), y + 120.0 * Sin(a))
        else
            call FF_PB_RingUnit(lane, 4, FF_PB_p, 'hfoo', x + 120.0 * Cos(a), y + 120.0 * Sin(a))
        endif
        set k = k + 1
    endloop
endfunction

function FF_PB_Losses takes integer lane returns string
    local integer k = 0
    local string s = ""
    local unit u
    loop
        exitwhen k >= 5
        set u = FF_PB_lane[lane * 8 + k]
        set s = s + " " + FF_PB_Id2S(GetUnitTypeId(u))
        if GetOwningPlayer(u) == FF_PB_p then
            set s = s + "(own)"
        endif
        set s = s + "=" + I2S(R2I(10000.0 - GetWidgetLife(u)))
        set k = k + 1
    endloop
    return s
endfunction

// ---------------------------------------------------------------------------------------------- DW: Death Ward (main trigger, replicated)
function FF_PB_WardEnd takes nothing returns nothing
    local integer lane = 1
    call DestroyTimer(GetExpiredTimer())
    loop
        exitwhen lane > 3
        call FF_PB_Log("DW L" + I2S(lane + 3) + " (free targets) lost_8.7s:" + FF_PB_Losses(lane))
        set lane = lane + 1
    endloop
    call FF_PB_Cleanup()
    call TimerStart(CreateTimer(), 0.5, false, function FF_PB_Finish)
endfunction

// lanes 1-3: Death Ward L4/L5/L6 exactly like Trig_HERO_Death_Wards, against free-standing enemy footmen
function FF_PB_WardStart takes nothing returns nothing
    local integer lane = 1
    local integer lvl
    local real x
    local real y
    local unit w
    local unit d
    call DestroyTimer(GetExpiredTimer())
    loop
        exitwhen lane > 3
        set lvl = lane + 3
        set x = FF_PB_LaneX(lane)
        set y = FF_PB_LaneY(lane)
        call FF_PB_EnemyRingP(lane, x, y, false)
        set w = FF_PB_Track(CreateUnit(FF_PB_p, 'o011', x, y, 270.0))
        call SetUnitAbilityLevel(w, 'A0IP', lvl)
        call SetUnitAbilityLevel(w, 'A0F6', lvl)
        call SetUnitAbilityLevel(w, 'A0F0', lvl)
        call UnitApplyTimedLife(w, 'Bhwd', 8.5)
        set d = FF_PB_Track(CreateUnit(FF_PB_p, 'dmmy', x, y, 270.0))
        call UnitAddAbility(d, 'A0F6')
        call SetUnitAbilityLevel(d, 'A0F6', lvl)
        call IssueImmediateOrder(d, "thunderclap")
        call UnitApplyTimedLife(d, 'BTLF', 0.10)
        set lane = lane + 1
    endloop
    call TimerStart(CreateTimer(), 8.7, false, function FF_PB_WardEnd)
endfunction

// ---------------------------------------------------------------------------------------------- BZ + DR as shipped
function FF_PB_BlizzEnd takes nothing returns nothing
    local integer lane = 1
    call DestroyTimer(GetExpiredTimer())
    loop
        exitwhen lane > 6
        call FF_PB_Log("BZ lane" + I2S(lane) + " L" + I2S(GetUnitAbilityLevel(FF_PB_lane[lane * 8 + 7], 'AHbz')) + " lost_14s:" + FF_PB_Losses(lane))
        set lane = lane + 1
    endloop
    call FF_PB_Cleanup()
    call TimerStart(CreateTimer(), 0.5, false, function FF_PB_Finish)
endfunction

// lanes 1-3: Blizzard L1/L4/L6 on an enemy scout tower + 4 footmen | lanes 4-6: L2/L5/L6 on the mixed ring
// (expected with the map fix Hbz4 = 0: the tower takes 0, every other ring unit takes the level's damage)
function FF_PB_BlizzStart takes nothing returns nothing
    local integer lane = 1
    local integer k
    local integer lvl
    local real x
    local real y
    local unit c
    local integer array lv
    set lv[1] = 1
    set lv[2] = 4
    set lv[3] = 6
    set lv[4] = 2
    set lv[5] = 5
    set lv[6] = 6
    call DestroyTimer(GetExpiredTimer())
    loop
        exitwhen lane > 6
        set lvl = lv[lane]
        set x = FF_PB_LaneX(lane)
        set y = FF_PB_LaneY(lane)
        if lane <= 3 then
            call FF_PB_Ring(lane, 1, x, y)
        else
            call FF_PB_Ring(lane, 0, x, y)
        endif
        set c = FF_PB_Track(CreateUnit(FF_PB_p, 'H008', x - 450.0, y, 0.0))
        call SetUnitInvulnerable(c, true)
        call UnitRemoveAbility(c, 'Aatk')
        call SetHeroLevel(c, 25, false)
        set k = 0
        loop
            exitwhen k >= lvl
            call SelectHeroSkill(c, 'AHbz')
            set k = k + 1
        endloop
        call BlzSetUnitMaxMana(c, 10000)
        call SetUnitState(c, UNIT_STATE_MANA, 10000.0)
        set FF_PB_lane[lane * 8 + 7] = c
        call FF_PB_Log("BZ lane" + I2S(lane) + " L" + I2S(GetUnitAbilityLevel(c, 'AHbz')) + " buildingDamage(Hbz4)=" + FF_PB_ReadReal(c, 'AHbz', 'Hbz4', lvl) + " order=" + FF_PB_B2S(IssuePointOrder(c, "blizzard", x, y)))
        set lane = lane + 1
    endloop
    call TimerStart(CreateTimer(), 14.0, false, function FF_PB_BlizzEnd)
endfunction

// ---------------------------------------------------------------------------------------------- read-back + start
function FF_PB_ReadTick takes nothing returns nothing
    if FF_PB_ReadEntries(150) then
        call PauseTimer(GetExpiredTimer())
        call DestroyTimer(GetExpiredTimer())
        call UnitRemoveAbility(FF_PB_dummy, FF_PB_curAbil)
        call RemoveUnit(FF_PB_dummy)
        call FF_PB_Say("PROBE: read-back done (" + I2S(FF_PB_n) + " cells), running Blizzard vs buildings...")
        call TimerStart(CreateTimer(), 1.0, false, function FF_PB_BlizzStart)
    endif
endfunction

function FF_PB_Start takes nothing returns nothing
    local group tmp = CreateGroup()
    local unit u
    local integer i = 0
    call DestroyTimer(GetExpiredTimer())
    loop
        exitwhen i >= bj_MAX_PLAYERS
        if FF_PB_p == null and GetPlayerSlotState(Player(i)) == PLAYER_SLOT_STATE_PLAYING and GetPlayerController(Player(i)) == MAP_CONTROL_USER then
            set FF_PB_p = Player(i)
        endif
        set i = i + 1
    endloop
    if FF_PB_p == null then
        set FF_PB_p = Player(0)
    endif
    set FF_PB_e = Player(PLAYER_NEUTRAL_AGGRESSIVE)
    set FF_PB_cx = GetRectCenterX(bj_mapInitialPlayableArea)
    set FF_PB_cy = GetRectCenterY(bj_mapInitialPlayableArea)
    set FF_PB_g = CreateGroup()
    call FogEnable(false)
    call FogMaskEnable(false)
    call GroupEnumUnitsInRange(tmp, FF_PB_cx, FF_PB_cy, 3000.0, null)
    loop
        set u = FirstOfGroup(tmp)
        exitwhen u == null
        call GroupRemoveUnit(tmp, u)
        call RemoveUnit(u)
    endloop
    call DestroyGroup(tmp)
    if GetLocalPlayer() == FF_PB_p then
        call SetCameraPosition(FF_PB_cx, FF_PB_cy)
    endif
    call FF_PB_LoadData()
    call FF_PB_Say("|cffffcc00FF 3.0 PROBE v6|r - " + I2S(FF_PB_n) + " ability cells. Please wait ~25 seconds for PROBE DONE.")
    set FF_PB_dummy = CreateUnit(Player(PLAYER_NEUTRAL_PASSIVE), 'hfoo', FF_PB_cx + 2900.0, FF_PB_cy - 2900.0, 0.0)
    call PauseUnit(FF_PB_dummy, true)
    call ShowUnit(FF_PB_dummy, false)
    call TimerStart(CreateTimer(), 0.02, true, function FF_PB_ReadTick)
endfunction

// Injected by the build runner right after `call FF_Init()` (FF_JASS_MAP_ADDONS).
function FF_MapInit takes nothing returns nothing
    call TimerStart(CreateTimer(), 1.0, false, function FF_PB_Start)
endfunction
