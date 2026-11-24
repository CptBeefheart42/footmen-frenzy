-- Check actual damage events, including critical pulses and the edge of the pylon landing.
T.lobby()
T.boot()
local enemySlot = T.map == "799x" and 4 or 5
local x, y = 6500, 6500
local hero = T.unit(1, "H043", x, y)
local inside = T.unit(enemySlot, "hfoo", x + 162.4, y)
local outside = T.unit(enemySlot, "hfoo", x + 162.6, y)
local hits = {}
function UnitDamageTarget(source, victim, value)
    if source == hero then hits[victim] = (hits[victim] or 0) + value end
    return true
end
T.check("Time Warp damage by spell rank", function()
    local values = {85, 120, 190, 285, 375, 575}
    for rank, expected in ipairs(values) do
        hits = {}
        GTW_Caster[1], GTW_Rank[1], GTW_Hit[1] = hero, rank, CreateGroup()
        GroupAddUnit(GTW_Hit[1], inside)
        GTW_Explode(1)
        T.eq(hits[inside], expected, "rank " .. rank)
    end
end)
T.check("Guardian Shield normal and double pulses", function()
    T.unitType("hfoo", {life = 420})
    local ally = T.unit(1, "hfoo", x + 50, y)
    local values = {50, 75, 100}
    for rank, expected in ipairs(values) do
        SetUnitAbilityLevel(hero, GD_ABILITY, rank)
        for _, multiplier in ipairs({1, 2}) do
            hits = {}
            local originalRandom = GetRandomInt
            GetRandomInt = function() return multiplier == 2 and 1 or 4 end
            SetWidgetLife(ally, 1)
            GD_Pulse(hero, x, y)
            GetRandomInt = originalRandom
            T.eq(GetWidgetLife(ally), 1 + expected * multiplier, "ally healing at rank " .. rank)
            T.eq(hits[inside], expected * multiplier, "rank " .. rank .. ", multiplier " .. multiplier)
        end
    end
end)

T.check("Psionic Recall hits on landing, at the six requested ranks", function()
    local ally = T.unit(1, "hfoo", x + 110, y)
    for rank, expected in ipairs({40, 70, 90, 120, 140, 200}) do
        hits = {}
        TFP_FFDP_Caster[1], TFP_FFDP_Owner[1] = hero, GetOwningPlayer(hero)
        TFP_FFDP_Lantern[1] = T.unit(1, "hfoo", x, y)
        TFP_FFDP_Level[1], TFP_FFDP_Tx[1], TFP_FFDP_Ty[1] = rank, x, y
        TFP_FFDP_Plant(1)
        T.eq(hits[inside], expected, "enemy just inside the landing radius at rank " .. rank)
        T.eq(hits[outside], nil, "enemy just outside the landing radius")
        T.eq(hits[ally], nil, "allied unit takes no damage")
    end
end)

T.check("Guardian Shield pulses once per second for the rank duration", function()
    local getUnit, getAbility, pulse = GetTriggerUnit, GetSpellAbilityId, GD_Pulse
    GetTriggerUnit = function() return hero end
    GetSpellAbilityId = function() return GD_ABILITY end
    for rank, duration in ipairs({10, 12, 15}) do
        local pulses = 0
        GD_Pulse = function() pulses = pulses + 1 end
        SetUnitAbilityLevel(hero, GD_ABILITY, rank)
        GD_Cast()
        T.eq(GD_Left[GD_Count] * GD_PERIOD, duration, "duration at rank " .. rank)
        for tick = 1, duration * 20 do GD_Tick() end
        T.eq(pulses, duration, "pulse count at rank " .. rank)
        T.eq(GD_Count, 0, "shield expired")
    end
    GetTriggerUnit, GetSpellAbilityId, GD_Pulse = getUnit, getAbility, pulse
end)
