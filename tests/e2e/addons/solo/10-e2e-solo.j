// e2e scenario "solo" (Solo 1v1v1v1 map only): one short deathmatch game played to its end by script, the client as
// slot 1 (Player 0), computers in the other three Solo seats (slots 5, 8, 12 — `slots` file). AFK host: the map
// starts its pub game itself, King of the Hill always on (the hill stands from the start).
//   t~3     heroes for the four seats (created in the tavern area: the map's TP_hero makes them the seats' heroes)
//   chat    -kd (typed by tests/e2e/run.py: `use,1,cmd`)
//   then    slot 1's hero kills an own footman (deny_own), an enemy footman and slot 5's hero; takes the hill
//   t>=95   (after Solo's tier-1 tech delay) slot 1 buys an item and a creep, researches attack + armor
//   t>=125  (bases vulnerable at 120s) the bases of slots 5, 8, 12 fall: placements team1, team4, team3, team2

globals
    unit FF_E2E_hero = null
    integer FF_E2E_waited = 0
    integer FF_E2E_uk0 = 0
    integer FF_E2E_hk0 = 0
    integer FF_E2E_item = 0
endglobals

function FF_E2E_SoloFinish takes nothing returns nothing
    call FF_E2E_Done()
endfunction

// From 125s (bases are vulnerable at 120s): the bases of slots 5, 8, 12 fall in this order.
function FF_E2E_SoloEndgame takes nothing returns nothing
    if FF_E2E_Now() < 125 then
        call FF_E2E_After(2.0, function FF_E2E_SoloEndgame)
        return
    endif
    call FF_E2E_AddBase(5)
    call FF_E2E_AddBase(8)
    call FF_E2E_AddBase(12)
    call FF_E2E_EndGame(false, function FF_E2E_SoloFinish)
endfunction

function FF_E2E_SoloBought takes nothing returns nothing
    call FF_E2E_Row("bought,item=" + FF_E2E_Bool(UnitHasItemOfTypeBJ(FF_E2E_hero, FF_E2E_item)) + ",Rhme=" + I2S(GetPlayerTechCount(Player(0), 'Rhme', true)) + ",Rhar=" + I2S(GetPlayerTechCount(Player(0), 'Rhar', true)) + ",t=" + I2S(FF_E2E_Now()))
    call FF_E2E_SoloEndgame()
endfunction

function FF_E2E_SoloResearch takes nothing returns nothing
    local unit base = udg_base[1]
    call FF_E2E_Row("research,base=" + FF_us_Id2S(GetUnitTypeId(base)) + ",o1=" + FF_E2E_Bool(IssueImmediateOrderById(base, 'Rhme')) + ",o2=" + FF_E2E_Bool(IssueImmediateOrderById(base, 'Rhar')) + ",t=" + I2S(FF_E2E_Now()))
    call FF_E2E_After(20.0, function FF_E2E_SoloBought)
    set base = null
endfunction

function FF_E2E_SoloCreep takes nothing returns nothing
    local real sx = GetStartLocationX(GetPlayerStartLocation(Player(0)))
    local real sy = GetStartLocationY(GetPlayerStartLocation(Player(0)))
    local unit shop = FF_E2E_Nearest(Player(PLAYER_NEUTRAL_PASSIVE), 'n00R', sx, sy)
    if shop == null then
        call FF_E2E_Row("creep,shop=0")
    else
        call SetUnitPosition(FF_E2E_hero, GetUnitX(shop) + 150.0, GetUnitY(shop) - 150.0)
        call FF_E2E_Row("creep,order=" + FF_E2E_Bool(IssueNeutralImmediateOrderById(Player(0), shop, 'n00Q')) + ",t=" + I2S(FF_E2E_Now()))
    endif
    call FF_E2E_After(2.0, function FF_E2E_SoloResearch)
    set shop = null
endfunction

function FF_E2E_SoloItemBuy takes nothing returns nothing
    set FF_E2E_item = FF_E2E_soldItem
    call FF_E2E_Row("item,via=key,id=" + FF_us_Id2S(FF_E2E_item) + ",t=" + I2S(FF_E2E_Now()))
    if FF_E2E_item == 0 then
        set FF_E2E_item = FF_E2E_BuyFirstItem(FF_E2E_hero, gg_unit_n01B_0055)
    endif
    call SetUnitInvulnerable(FF_E2E_hero, true)
    if GetLocalPlayer() == Player(0) then
        call ClearSelection()
        call SelectUnit(FF_E2E_hero, true)
    endif
    call FF_E2E_After(1.0, function FF_E2E_SoloCreep)
endfunction

// Solo refuses shop and research orders before its tier-1 tech delay (90s).
function FF_E2E_SoloShop takes nothing returns nothing
    if FF_E2E_Now() < 95 then
        call FF_E2E_After(2.0, function FF_E2E_SoloShop)
        return
    endif
    call SetPlayerState(Player(0), PLAYER_STATE_RESOURCE_GOLD, 20000)
    call FF_E2E_BuyByKey(FF_E2E_hero, gg_unit_n01B_0055, function FF_E2E_SoloItemBuy)
endfunction

function FF_E2E_SoloKothRead takes nothing returns nothing
    call FF_E2E_Row("koth,holder=" + I2S(GetPlayerId(udg_KOTH_Player) + 1) + ",gold1=" + I2S(FF_st_kothGold[1]) + ",t=" + I2S(FF_E2E_Now()))
    call FF_E2E_SoloShop()
endfunction

function FF_E2E_SoloKoth takes nothing returns nothing
    if udg_KOTH_Hill == null or not FF_UnitAlive(udg_KOTH_Hill) then
        set FF_E2E_waited = FF_E2E_waited + 2
        if FF_E2E_waited > 120 then
            call FF_E2E_Row("koth,timeout=120")
            call FF_E2E_SoloEndgame()
            return
        endif
        call FF_E2E_After(2.0, function FF_E2E_SoloKoth)
        return
    endif
    call FF_E2E_Row("koth,take=1,t=" + I2S(FF_E2E_Now()))
    call SetUnitPosition(FF_E2E_hero, GetUnitX(udg_KOTH_Hill) + 150.0, GetUnitY(udg_KOTH_Hill))
    call FF_E2E_Kill(FF_E2E_hero, udg_KOTH_Hill)
    call FF_E2E_After(20.0, function FF_E2E_SoloKothRead)
endfunction

function FF_E2E_SoloKillsRead takes nothing returns nothing
    call FF_E2E_Row("kills,slot=1,ukills0=" + I2S(FF_E2E_uk0) + ",ukills1=" + I2S(udg_unit_kills[1]) + ",hkills0=" + I2S(FF_E2E_hk0) + ",hkills1=" + I2S(udg_hero_kills[1]) + ",deny_own=" + I2S(FF_st_denyOwn[1]))
    set FF_E2E_waited = 0
    call FF_E2E_SoloKoth()
endfunction

function FF_E2E_SoloKills takes nothing returns nothing
    local real x = GetUnitX(FF_E2E_hero)
    local real y = GetUnitY(FF_E2E_hero)
    set FF_E2E_uk0 = udg_unit_kills[1]
    set FF_E2E_hk0 = udg_hero_kills[1]
    call FF_E2E_Kill(FF_E2E_hero, CreateUnit(Player(0), 'hfoo', x + 100.0, y, 0.0))
    call FF_E2E_Kill(FF_E2E_hero, CreateUnit(Player(4), 'hfoo', x + 100.0, y - 100.0, 0.0))
    call FF_E2E_Kill(FF_E2E_hero, udg_herO[5])
    call FF_E2E_After(2.0, function FF_E2E_SoloKillsRead)
endfunction
function FF_E2E_SoloItem takes nothing returns nothing
    call FF_E2E_Row("hero,1=" + FF_us_Id2S(GetUnitTypeId(udg_herO[1])) + ",5=" + FF_us_Id2S(GetUnitTypeId(udg_herO[5])) + ",8=" + FF_us_Id2S(GetUnitTypeId(udg_herO[8])) + ",12=" + FF_us_Id2S(GetUnitTypeId(udg_herO[12])))
    set FF_E2E_hero = udg_herO[1]
    call SetUnitInvulnerable(FF_E2E_hero, true)
    call FF_E2E_WaitChat("-kd", function FF_E2E_SoloKills)
endfunction

// The host's game-type dialog: "Normal Game (Standard)", the first of Solo's two buttons (measured on a 1402x824
// window: the dialog is centred, so the position scales with the window).
function FF_E2E_HostClick takes nothing returns string
    return "0.5 0.542"
endfunction

function FF_E2E_Scenario takes nothing returns nothing
    call FF_E2E_Begin("solo")
    call CreateUnit(Player(0), 'H005', -2600.0, -300.0, 0.0)
    call CreateUnit(Player(4), 'H005', -2600.0, -300.0, 0.0)
    call CreateUnit(Player(7), 'H005', -2600.0, -300.0, 0.0)
    call CreateUnit(Player(11), 'H005', -2600.0, -300.0, 0.0)
    call FF_E2E_After(3.0, function FF_E2E_SoloItem)
endfunction
