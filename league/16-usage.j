// FF addons — Usage: which heroes, spells, items, units, upgrades, towers, modes and chat commands a game uses,
// written into ff_result by 20-gameresult.j's flush (format: docs/result-contract.md; raw object codes, names
// are joined on the website):
//   use,<slot>,<cat>,<code>=<n>,...      per-slot counters; cat = item | unit | tech | tower | spell | cmd | pawn
//                                        | rsch | rlvl
//   skills,<slot>,<hero>,<abil>;<abil>;...  the order the hero learned its abilities (skill build)
//   pick,<t>,<slot>,<hero>,pick|repick|swap|altar   and   baseup,<t>,<slot>,<new base type>   (events)
//   buy,<t>,<slot>,<code>   and   used,<t>,<slot>,<code>   (events: the key items of FF_us_IsTimedBuy / IsTimedUse)
//   modes,<k>=<v>,...                     once, when the game's modes are final
//   koth,<side>,hold=<seconds>,caps=<n>  King of the Hill, per side: team1..team4, or west / east in 6v6 (as out/placement)
// Long use/skills rows are split into chunks of at most FF_PRELOAD_MAX chars (never inside a pair or an ability);
// the bot unions them. Rows are rebuilt only for slots whose counters changed: every JASS string lives until the
// game ends. Nothing lumber-related is tracked.
//   * item: items bought — counted in FF_EarlyInit's handler, registered BEFORE the map's own triggers, because the
//     map's courier ("packhorse") purchase removes the bought item and drops a replacement in its handler.
//   * unit: units bought (heroes, creeps, mercenaries), checked one tick later: shop page buttons, game-mode
//     selector units, creeps over the team limit (refunded) and Solo's altar over its limit are removed by the map
//     in the same thread, so they are gone by then and not counted. A non-hero unit with a creep price (the map
//     keeps it in the unit's lumber-bounty field; its limit trigger reads and clears it) is a hired creep.
//   * tech: upgrades researched by THIS player, value = level reached; team copies the map hands to allies fire
//     no research event. A research at the team's shared building (n003) is also team_res in the stats row.
//   * rsch / rlvl: per upgrade, the levels THIS player researched and the sum of those levels. The levels a player
//     paid for are exactly these: allies' team copies, the levels the map hands out at the start and Overdrive's
//     fire no research event. An upgrade costing base + step * (level - 1) cost base * rsch + step * (rlvl - rsch).
//   * pawn: items sold back to a shop, credited to the player whose unit sold them.
//   * tower: tower upgrades finished, by resulting type (hwtw = back to a scout tower). A base upgrade (town hall
//     or one of the map's base types) is a baseup event instead.
//   * spell: spells cast by a hero that learned that ability — item spells, dummy casters and illusions excluded.
//   * cmd: chat commands, by command without the dash. Spam-safe: one O(1)-ish handler per message, at most
//     FF_US_CHAT_BURST messages per player per second are looked at, counts capped, nothing written per message.
// All reads are synced game state; the only write is the existing local Preload of ff_result.

globals
    hashtable FF_us_ht = InitHashtable()
    // Learned hero abilities: parent = hero handle id, child = ability id.
    hashtable FF_us_learned = InitHashtable()
    integer FF_US_CHAT_BURST = 4
    integer FF_US_CMD_CAP = 999
    // Counter categories (the `use` rows' <cat>, FF_us_catName).
    integer FF_US_ITEM = 1
    integer FF_US_UNIT = 2
    integer FF_US_TECH = 3
    integer FF_US_TOWER = 4
    integer FF_US_SPELL = 5
    integer FF_US_CMD = 6
    integer FF_US_PAWN = 7
    integer FF_US_RSCH = 8
    integer FF_US_RLVL = 9
    integer FF_US_CATS = 9
    // Caps: events per game, units sold per tick, heroes per slot, learned abilities per hero.
    integer FF_US_EVENT_MAX = 400
    integer FF_US_SOLD_MAX = 64
    integer FF_US_HERO_MAX = 16
    integer FF_US_SKILL_MAX = 64
    // The maps fill udg_base_type[0..50].
    integer FF_US_BASE_TYPES = 50
    // Hashtable layout of FF_us_ht (the parent keys come from the FF_us_*Key functions):
    //   counters  FF_us_CountKey(slot, cat), child = code -> count; the codes in first-seen order under
    //             FF_us_OrderKey(slot, cat), child 0..FF_us_n[FF_us_CountKey(slot, cat)] - 1
    //   rows      FF_us_RowKey(slot), child 0..FF_us_rowN[slot] - 1: the slot's cached rows
    //   heroes    FF_us_HeroSlotKey(slot, h), hero h's skill build: child -1 = hero type, -2 = hero handle id,
    //             -3 = ability count, 0.. = abilities in learn order
    integer array FF_us_n
    string array FF_us_catName
    boolean array FF_us_dirty
    integer array FF_us_rowN
    integer array FF_us_heroN
    // Events (pick / baseup).
    string array FF_us_events
    integer FF_us_eventN = 0
    boolean FF_us_sharedDirty = false
    // Hero picks, polled from the map's per-slot hero globals.
    unit array FF_us_heroSeen
    boolean array FF_us_hadHero
    boolean array FF_us_swapSeen
    // Sold units waiting one tick for the map's own handlers.
    unit array FF_us_sold
    unit array FF_us_seller
    integer array FF_us_soldCost
    integer FF_us_soldN = 0
    timer FF_us_soldTimer = null
    // King of the Hill per side (1..4).
    integer array FF_us_kothHold
    integer array FF_us_kothCaps
    player FF_us_kothLast = null
    // Modes: the row once final; map addons append their own keys through FF_us_modeHook / FF_us_modeExtra.
    string FF_us_modes = null
    trigger FF_us_modeHook = null
    string FF_us_modeExtra = ""
    // Chat commands (with the dash), how many messages a player sent this second.
    string array FF_us_cmd
    integer FF_us_cmdN = 0
    integer array FF_us_chatBurst
    string FF_us_chars = " !\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~"
endglobals

function FF_us_CountKey takes integer slot, integer cat returns integer
    return slot * 16 + cat
endfunction

function FF_us_OrderKey takes integer slot, integer cat returns integer
    return 1000 + slot * 16 + cat
endfunction

function FF_us_RowKey takes integer slot returns integer
    return 5000 + slot
endfunction

function FF_us_HeroSlotKey takes integer slot, integer h returns integer
    return 6000 + slot * 16 + h
endfunction

function FF_us_Char takes integer c returns string
    if c < 32 or c > 126 then
        return "?"
    endif
    return SubString(FF_us_chars, c - 32, c - 31)
endfunction

// A raw object code ('hfoo') as its 4 characters.
function FF_us_Id2S takes integer id returns string
    return FF_us_Char(id / 16777216) + FF_us_Char(ModuloInteger(id / 65536, 256)) + FF_us_Char(ModuloInteger(id / 256, 256)) + FF_us_Char(ModuloInteger(id, 256))
endfunction

function FF_us_Bit takes boolean b returns string
    if b then
        return "1"
    endif
    return "0"
endfunction

// Adds v (or, with assign, stores v) under the slot's category counter for code.
function FF_us_Put takes integer slot, integer cat, integer oid, integer v, boolean assign returns nothing
    local integer key = FF_us_CountKey(slot, cat)
    if slot < 1 or slot > 12 then
        return
    endif
    if not HaveSavedInteger(FF_us_ht, key, oid) then
        call SaveInteger(FF_us_ht, FF_us_OrderKey(slot, cat), FF_us_n[key], oid)
        set FF_us_n[key] = FF_us_n[key] + 1
        call SaveInteger(FF_us_ht, key, oid, 0)
    endif
    if not assign then
        set v = LoadInteger(FF_us_ht, key, oid) + v
    endif
    call SaveInteger(FF_us_ht, key, oid, v)
    set FF_us_dirty[slot] = true
endfunction

function FF_us_Add takes integer slot, integer cat, integer oid returns nothing
    call FF_us_Put(slot, cat, oid, 1, false)
endfunction

function FF_us_AddEvent takes string line returns nothing
    if FF_us_eventN < FF_US_EVENT_MAX then
        set FF_us_events[FF_us_eventN] = line
        set FF_us_eventN = FF_us_eventN + 1
        set FF_us_sharedDirty = true
    endif
endfunction

// --- row building ---------------------------------------------------------------------------------------------

function FF_us_EmitRow takes integer slot, string row returns nothing
    call SaveStr(FF_us_ht, FF_us_RowKey(slot), FF_us_rowN[slot], row)
    set FF_us_rowN[slot] = FF_us_rowN[slot] + 1
endfunction

// Appends `entry` (a k=v pair or an ability) to the chunk being built; starts a new chunk when it would not fit.
// Returns the chunk being built. `sep` separates items inside a chunk.
function FF_us_Append takes integer slot, string head, string cur, string entry, string sep returns string
    if cur == null then
        return head + entry
    endif
    if StringLength(cur) + StringLength(sep) + StringLength(entry) > FF_PRELOAD_MAX then
        call FF_us_EmitRow(slot, cur)
        return head + entry
    endif
    return cur + sep + entry
endfunction

// One code of a counter category as "<code>=<count>" (a chat command without its dash).
function FF_us_Entry takes integer slot, integer cat, integer oid returns string
    local string name
    if cat == FF_US_CMD then
        set name = SubString(FF_us_cmd[oid], 1, StringLength(FF_us_cmd[oid]))
    else
        set name = FF_us_Id2S(oid)
    endif
    return name + "=" + I2S(LoadInteger(FF_us_ht, FF_us_CountKey(slot, cat), oid))
endfunction

// Rebuilds the slot's cached rows: one `use` row (or more chunks) per category, then one `skills` row per hero.
function FF_us_BuildRows takes integer slot returns nothing
    local integer cat = 1
    local integer key
    local integer i
    local integer h
    local integer oid
    local integer n
    local string head
    local string cur
    set FF_us_rowN[slot] = 0
    loop
        exitwhen cat > FF_US_CATS
        set key = FF_us_CountKey(slot, cat)
        if FF_us_n[key] > 0 then
            set head = "use," + I2S(slot) + "," + FF_us_catName[cat] + ","
            set cur = null
            set i = 0
            loop
                exitwhen i >= FF_us_n[key]
                set oid = LoadInteger(FF_us_ht, FF_us_OrderKey(slot, cat), i)
                set cur = FF_us_Append(slot, head, cur, FF_us_Entry(slot, cat, oid), ",")
                set i = i + 1
            endloop
            call FF_us_EmitRow(slot, cur)
        endif
        set cat = cat + 1
    endloop
    set h = 0
    loop
        exitwhen h >= FF_us_heroN[slot]
        set key = FF_us_HeroSlotKey(slot, h)
        set n = LoadInteger(FF_us_ht, key, -3)
        if n > 0 then
            set head = "skills," + I2S(slot) + "," + FF_us_Id2S(LoadInteger(FF_us_ht, key, -1)) + ","
            set cur = null
            set i = 0
            loop
                exitwhen i >= n
                set cur = FF_us_Append(slot, head, cur, FF_us_Id2S(LoadInteger(FF_us_ht, key, i)), ";")
                set i = i + 1
            endloop
            call FF_us_EmitRow(slot, cur)
        endif
        set h = h + 1
    endloop
endfunction

// Rebuilds the slot's use/skills rows if its counters changed; true if they did.
function FF_us_Refresh takes integer slot returns boolean
    if not FF_us_dirty[slot] then
        return false
    endif
    set FF_us_dirty[slot] = false
    call FF_us_BuildRows(slot)
    return true
endfunction

// True (once) if the events, modes or KOTH rows changed since the last call.
function FF_us_RefreshShared takes nothing returns boolean
    local boolean changed = FF_us_sharedDirty
    set FF_us_sharedDirty = false
    return changed
endfunction

// Called by FF_gr_Flush between PreloadGenStart and PreloadGenEnd.
function FF_us_PreloadEvents takes nothing returns nothing
    local integer i = 0
    loop
        exitwhen i >= FF_us_eventN
        call Preload(FF_us_events[i])
        set i = i + 1
    endloop
endfunction

// The modes row and one koth row per side that held the hill.
function FF_us_PreloadShared takes nothing returns nothing
    local integer side = 1
    if FF_us_modes != null then
        call Preload(FF_us_modes)
    endif
    loop
        exitwhen side > 4
        if FF_us_kothHold[side] > 0 or FF_us_kothCaps[side] > 0 then
            call Preload("koth," + FF_SideLabel(side) + ",hold=" + I2S(FF_us_kothHold[side]) + ",caps=" + I2S(FF_us_kothCaps[side]))
        endif
        set side = side + 1
    endloop
endfunction

function FF_us_PreloadSlot takes integer slot returns nothing
    local integer i = 0
    loop
        exitwhen i >= FF_us_rowN[slot]
        call Preload(LoadStr(FF_us_ht, FF_us_RowKey(slot), i))
        set i = i + 1
    endloop
endfunction

// --- purchases ------------------------------------------------------------------------------------------------

// Purchases written with their time: Ring of J33bus, Sword of a Thousand Truths (both versions), Altar of the Gods.
function FF_us_IsTimedBuy takes integer id returns boolean
    return id == 'I002' or id == 'I01Z' or id == 'I048' or id == 'o00B'
endfunction

// Item uses written with their time: Penguin Stone, Healing Wards of the Gods.
function FF_us_IsTimedUse takes integer id returns boolean
    return id == 'I033' or id == 'I005'
endfunction

function FF_us_TimedEvent takes string kind, integer slot, integer id returns nothing
    call FF_us_AddEvent(kind + "," + FF_Elapsed() + "," + I2S(slot) + "," + FF_us_Id2S(id))
endfunction

function FF_us_OnItemSold takes nothing returns nothing
    local integer s = FF_st_Slot(GetOwningPlayer(GetBuyingUnit()))
    local integer id = GetItemTypeId(GetSoldItem())
    call FF_us_Add(s, FF_US_ITEM, id)
    if s > 0 and FF_us_IsTimedBuy(id) then
        call FF_us_TimedEvent("buy", s, id)
    endif
endfunction

function FF_us_OnItemUsed takes nothing returns nothing
    local integer s = FF_st_Slot(GetOwningPlayer(GetTriggerUnit()))
    local integer id = GetItemTypeId(GetManipulatedItem())
    if s > 0 and FF_us_IsTimedUse(id) then
        call FF_us_TimedEvent("used", s, id)
    endif
endfunction

// An item sold back to a shop: the selling unit is the player's, the buying unit the shop.
function FF_us_OnItemPawned takes nothing returns nothing
    local integer s = FF_st_Slot(GetOwningPlayer(GetSellingUnit()))
    if s == 0 then
        set s = FF_st_Slot(GetOwningPlayer(GetBuyingUnit()))
    endif
    call FF_us_Add(s, FF_US_PAWN, GetItemTypeId(GetSoldItem()))
endfunction

// One tick after a unit sale: counts the sold units the map's own handlers kept (a removed unit reads type 0),
// with an altar hero as a pick event and a unit with a creep price as a hired creep.
function FF_us_OnSoldTick takes nothing returns nothing
    local integer i = 0
    local unit u
    local integer s
    local integer id
    loop
        exitwhen i >= FF_us_soldN
        set u = FF_us_sold[i]
        set id = GetUnitTypeId(u)
        if id != 0 then
            set s = FF_st_Slot(GetOwningPlayer(u))
            if s > 0 then
                call FF_us_Add(s, FF_US_UNIT, id)
                if FF_us_IsTimedBuy(id) then
                    call FF_us_TimedEvent("buy", s, id)
                endif
                if IsUnitType(u, UNIT_TYPE_HERO) then
                    // 'hhou': Solo's hero altar
                    if GetUnitTypeId(FF_us_seller[i]) == 'hhou' then
                        call FF_us_AddEvent("pick," + FF_Elapsed() + "," + I2S(s) + "," + FF_us_Id2S(id) + ",altar")
                    endif
                elseif FF_us_soldCost[i] > 0 then
                    set FF_st_creeps[s] = FF_st_creeps[s] + 1
                    set FF_st_creepGold[s] = FF_st_creepGold[s] + FF_us_soldCost[i]
                    call GroupAddUnit(FF_st_hired, u)
                endif
            endif
        endif
        set FF_us_sold[i] = null
        set FF_us_seller[i] = null
        set i = i + 1
    endloop
    set FF_us_soldN = 0
    set u = null
endfunction

function FF_us_OnUnitSold takes nothing returns nothing
    local unit u = GetSoldUnit()
    local integer cost = BlzGetUnitIntegerField(u, UNIT_IF_LUMBER_BOUNTY_AWARDED_BASE)
    // The map's creep-limit trigger reads and clears that field; if it handled this very sale first, its globals
    // hold the sold unit and its price.
    if cost == 0 and udg_temp_unit == u then
        set cost = udg_creep_gold_cost
    endif
    if FF_us_soldN < FF_US_SOLD_MAX then
        set FF_us_sold[FF_us_soldN] = u
        set FF_us_seller[FF_us_soldN] = GetSellingUnit()
        set FF_us_soldCost[FF_us_soldN] = cost
        set FF_us_soldN = FF_us_soldN + 1
        call TimerStart(FF_us_soldTimer, 0.0, false, function FF_us_OnSoldTick)
    endif
    set u = null
endfunction

// --- research, upgrades, heroes -------------------------------------------------------------------------------

function FF_us_OnResearch takes nothing returns nothing
    local unit u = GetTriggerUnit()
    local player p = GetOwningPlayer(u)
    local integer s = FF_st_Slot(p)
    local integer oid = GetResearched()
    local integer lvl = GetPlayerTechCount(p, oid, true)
    if s > 0 then
        call FF_us_Put(s, FF_US_TECH, oid, lvl, true)
        call FF_us_Add(s, FF_US_RSCH, oid)
        call FF_us_Put(s, FF_US_RLVL, oid, lvl, false)
        if GetUnitTypeId(u) == 'n003' then
            set FF_st_teamRes[s] = FF_st_teamRes[s] + 1
        endif
    endif
    set u = null
    set p = null
endfunction

// A town hall or one of the map's base types.
function FF_us_IsBase takes unit u returns boolean
    local integer id = GetUnitTypeId(u)
    local integer i = 0
    if IsUnitType(u, UNIT_TYPE_TOWNHALL) then
        return true
    endif
    loop
        exitwhen i > FF_US_BASE_TYPES
        if udg_base_type[i] == id then
            return true
        endif
        set i = i + 1
    endloop
    return false
endfunction

function FF_us_IsTower takes integer id returns boolean
    return id == 'hwtw' or id == 'etrp' or id == 'hgtw' or id == 'h05U' or id == 'hctw' or id == 'hatw' or id == 'h00S' or id == 'emow' or id == 'otrb' or id == 'owtw' or id == 'o01D'
endfunction

function FF_us_OnUpgrade takes nothing returns nothing
    local unit u = GetTriggerUnit()
    local integer s = FF_st_Slot(GetOwningPlayer(u))
    local integer id = GetUnitTypeId(u)
    if s > 0 then
        if FF_us_IsBase(u) then
            call FF_us_AddEvent("baseup," + FF_Elapsed() + "," + I2S(s) + "," + FF_us_Id2S(id))
        elseif FF_us_IsTower(id) then
            call FF_us_Add(s, FF_US_TOWER, id)
        endif
    endif
    set u = null
endfunction

// The skill-build entry of this hero in the slot's list, created on first use.
function FF_us_HeroKey takes integer slot, unit hero returns integer
    local integer h = 0
    local integer hid = GetHandleId(hero)
    local integer key
    loop
        exitwhen h >= FF_us_heroN[slot]
        set key = FF_us_HeroSlotKey(slot, h)
        if LoadInteger(FF_us_ht, key, -2) == hid then
            return key
        endif
        set h = h + 1
    endloop
    if h >= FF_US_HERO_MAX then
        return 0
    endif
    set key = FF_us_HeroSlotKey(slot, h)
    set FF_us_heroN[slot] = h + 1
    call SaveInteger(FF_us_ht, key, -1, GetUnitTypeId(hero))
    call SaveInteger(FF_us_ht, key, -2, hid)
    call SaveInteger(FF_us_ht, key, -3, 0)
    return key
endfunction

// A hero learned an ability: remembered for the spell counter, and appended to its skill build.
function FF_us_OnSkill takes nothing returns nothing
    local unit hero = GetTriggerUnit()
    local integer s = FF_st_Slot(GetOwningPlayer(hero))
    local integer abil = GetLearnedSkill()
    local integer key
    local integer n
    call SaveBoolean(FF_us_learned, GetHandleId(hero), abil, true)
    if s > 0 then
        set key = FF_us_HeroKey(s, hero)
        if key > 0 then
            set n = LoadInteger(FF_us_ht, key, -3)
            if n < FF_US_SKILL_MAX then
                call SaveInteger(FF_us_ht, key, n, abil)
                call SaveInteger(FF_us_ht, key, -3, n + 1)
                set FF_us_dirty[s] = true
            endif
        endif
    endif
    set hero = null
endfunction

function FF_us_OnSpell takes nothing returns nothing
    local unit u = GetTriggerUnit()
    local integer abil = GetSpellAbilityId()
    if IsUnitType(u, UNIT_TYPE_HERO) and not IsUnitIllusion(u) and LoadBoolean(FF_us_learned, GetHandleId(u), abil) then
        call FF_us_Add(FF_st_Slot(GetOwningPlayer(u)), FF_US_SPELL, abil)
    endif
    set u = null
endfunction

// --- chat commands --------------------------------------------------------------------------------------------

// Fills FF_us_cmd from a space-separated list of commands.
function FF_us_SetCommands takes string list returns nothing
    local integer len = StringLength(list)
    local integer from = 0
    local integer i = 0
    loop
        exitwhen i > len
        if i == len or SubString(list, i, i + 1) == " " then
            if i > from then
                set FF_us_cmd[FF_us_cmdN] = SubString(list, from, i)
                set FF_us_cmdN = FF_us_cmdN + 1
            endif
            set from = i + 1
        endif
        set i = i + 1
    endloop
endfunction

// A chat message: counted when it is a known command (followed by the end or a space), up to FF_US_CHAT_BURST
// messages per player per second.
function FF_us_OnChat takes nothing returns nothing
    local integer s = FF_st_Slot(GetTriggerPlayer())
    local string msg
    local integer len
    local integer cl
    local integer i = 0
    if s == 0 then
        return
    endif
    set FF_us_chatBurst[s] = FF_us_chatBurst[s] + 1
    if FF_us_chatBurst[s] > FF_US_CHAT_BURST then
        return
    endif
    set msg = GetEventPlayerChatString()
    if SubString(msg, 0, 1) != "-" then
        return
    endif
    set len = StringLength(msg)
    loop
        exitwhen i >= FF_us_cmdN
        set cl = StringLength(FF_us_cmd[i])
        if len >= cl and SubString(msg, 0, cl) == FF_us_cmd[i] and (len == cl or SubString(msg, cl, cl + 1) == " ") then
            if LoadInteger(FF_us_ht, FF_us_CountKey(s, FF_US_CMD), i) < FF_US_CMD_CAP then
                call FF_us_Add(s, FF_US_CMD, i)
            endif
            return
        endif
        set i = i + 1
    endloop
endfunction

// --- modes, KOTH, picks (polled) ------------------------------------------------------------------------------

// ",<key>=0|1" for a mode flag of the modes row.
function FF_us_Flag takes string key, boolean on returns string
    return "," + key + "=" + FF_us_Bit(on)
endfunction

// The game's modes are final (the AI hero-pick timer ran out): builds the modes row once, with the map addon's
// own keys from FF_us_modeHook.
function FF_us_OnModesFinal takes nothing returns nothing
    local string colossal = "0"
    local string s
    if udg_colossal_on then
        set colossal = I2S(udg_colossal_max_wave)
    endif
    set FF_us_modeExtra = ""
    if FF_us_modeHook != null then
        call TriggerExecute(FF_us_modeHook)
    endif
    set s = "modes,sel=" + I2S(udg_selected_mode) + FF_us_Flag("pub", udg_mode_pub) + FF_us_Flag("inhouse", udg_mode_inhouse)
    set s = s + FF_us_Flag("koth", udg_mode_koth) + FF_us_Flag("club777", udg_mode_777club)
    set s = s + FF_us_Flag("madness", udg_mode_madness) + FF_us_Flag("mirror", udg_mode_mirror)
    set s = s + FF_us_Flag("overdrive", udg_mode_overdrive) + ",colossal=" + colossal + FF_us_Flag("onev1", udg_mode_1v1)
    set s = s + FF_us_Flag("debug", udg_mode_debugmode) + FF_us_Flag("nomass", udg_mode_no_mass)
    set FF_us_modes = s + FF_us_Flag("strong", udg_mode_strong_mode) + FF_us_modeExtra
    set FF_us_sharedDirty = true
endfunction

// Hero picks, from the map's per-slot hero globals: a new hero is a pick, a repick or a swap.
function FF_us_PollPicks takes nothing returns nothing
    local integer s = 1
    local unit u
    local string how
    loop
        exitwhen s > 12
        set u = udg_herO[s]
        if u != FF_us_heroSeen[s] then
            if u != null then
                set how = "pick"
                if udg_swapped[s] and not FF_us_swapSeen[s] then
                    set how = "swap"
                    set FF_us_swapSeen[s] = true
                elseif FF_us_hadHero[s] then
                    set how = "repick"
                endif
                call FF_us_AddEvent("pick," + FF_Elapsed() + "," + I2S(s) + "," + FF_us_Id2S(GetUnitTypeId(u)) + "," + how)
                set FF_us_hadHero[s] = true
            endif
            set FF_us_heroSeen[s] = u
        endif
        set s = s + 1
    endloop
    set u = null
endfunction

// One second of King of the Hill: the holder's side gets a second of hold, and a capture when the holder changed.
function FF_us_PollKoth takes nothing returns nothing
    local integer ks
    local integer side
    if udg_KOTH_Player == null then
        return
    endif
    set ks = FF_st_Slot(udg_KOTH_Player)
    if ks > 0 then
        set side = FF_SideOf(ks)
        set FF_us_kothHold[side] = FF_us_kothHold[side] + 1
        if udg_KOTH_Player != FF_us_kothLast then
            set FF_us_kothCaps[side] = FF_us_kothCaps[side] + 1
        endif
        set FF_us_sharedDirty = true
    endif
    set FF_us_kothLast = udg_KOTH_Player
endfunction

function FF_us_ResetChatBurst takes nothing returns nothing
    local integer s = 1
    loop
        exitwhen s > 12
        set FF_us_chatBurst[s] = 0
        set s = s + 1
    endloop
endfunction

function FF_us_Poll takes nothing returns nothing
    call FF_us_ResetChatBurst()
    call FF_us_PollPicks()
    call FF_us_PollKoth()
    call FF_st_TmExpire()
endfunction

// --- init -----------------------------------------------------------------------------------------------------

// Runs from main() BEFORE the map's InitCustomTriggers (the build inserts the call), so these triggers fire
// ahead of the map's own on the same event.
function FF_EarlyInit takes nothing returns nothing
    local trigger t = CreateTrigger()
    call TriggerRegisterAnyUnitEventBJ(t, EVENT_PLAYER_UNIT_SELL_ITEM)
    call TriggerAddAction(t, function FF_us_OnItemSold)
    set t = null
endfunction

function FF_Usage_Init takes nothing returns nothing
    local trigger t
    local integer i = 0
    set FF_us_catName[FF_US_ITEM] = "item"
    set FF_us_catName[FF_US_UNIT] = "unit"
    set FF_us_catName[FF_US_TECH] = "tech"
    set FF_us_catName[FF_US_TOWER] = "tower"
    set FF_us_catName[FF_US_SPELL] = "spell"
    set FF_us_catName[FF_US_CMD] = "cmd"
    set FF_us_catName[FF_US_PAWN] = "pawn"
    set FF_us_catName[FF_US_RSCH] = "rsch"
    set FF_us_catName[FF_US_RLVL] = "rlvl"
    // Every chat command of both maps and the addons.
    call FF_us_SetCommands("-votekick -commands -players -forfeit -message -killme -reveal -guided -status -bounds")
    call FF_us_SetCommands("-bounty -repick -killa -mhoff -clear -debug -scale -mhon -time -swap -pool -next -help")
    call FF_us_SetCommands("-hero -kick -draw -gold -fog -cam -lvl -kd -ct -vk -p -t -c -i")
    call FF_us_SetCommands("-sub -obs")
    set FF_us_soldTimer = CreateTimer()
    set FF_st_hired = CreateGroup()
    set t = CreateTrigger()
    call TriggerRegisterAnyUnitEventBJ(t, EVENT_PLAYER_UNIT_SELL)
    call TriggerAddAction(t, function FF_us_OnUnitSold)
    set t = CreateTrigger()
    call TriggerRegisterAnyUnitEventBJ(t, EVENT_PLAYER_UNIT_PAWN_ITEM)
    call TriggerAddAction(t, function FF_us_OnItemPawned)
    set t = CreateTrigger()
    call TriggerRegisterAnyUnitEventBJ(t, EVENT_PLAYER_UNIT_USE_ITEM)
    call TriggerAddAction(t, function FF_us_OnItemUsed)
    set t = CreateTrigger()
    call TriggerRegisterAnyUnitEventBJ(t, EVENT_PLAYER_UNIT_RESEARCH_FINISH)
    call TriggerAddAction(t, function FF_us_OnResearch)
    set t = CreateTrigger()
    call TriggerRegisterAnyUnitEventBJ(t, EVENT_PLAYER_UNIT_UPGRADE_FINISH)
    call TriggerAddAction(t, function FF_us_OnUpgrade)
    set t = CreateTrigger()
    call TriggerRegisterAnyUnitEventBJ(t, EVENT_PLAYER_HERO_SKILL)
    call TriggerAddAction(t, function FF_us_OnSkill)
    set t = CreateTrigger()
    call TriggerRegisterAnyUnitEventBJ(t, EVENT_PLAYER_UNIT_SPELL_EFFECT)
    call TriggerAddAction(t, function FF_us_OnSpell)
    set t = CreateTrigger()
    loop
        exitwhen i >= 12
        call TriggerRegisterPlayerChatEvent(t, Player(i), "-", false)
        set i = i + 1
    endloop
    call TriggerAddAction(t, function FF_us_OnChat)
    set t = CreateTrigger()
    call TriggerRegisterTimerExpireEvent(t, udg_timer_AI_hero_pick)
    call TriggerAddAction(t, function FF_us_OnModesFinal)
    call TimerStart(CreateTimer(), 1.00, true, function FF_us_Poll)
    set t = null
endfunction
