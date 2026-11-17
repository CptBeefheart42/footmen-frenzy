// FF addons (main map only) — the main map's own keys of the `modes,` row (16-usage.j): pro mode, and
// "no transmute": the map has no flag for it, the mode takes the transmute heroes (category 11) out of the pool.
// Pro is either Pro flag of the map: the mode dialog's (FFR4Pro) or the mode shop's (udg_mode_promode).

function FF_MM_Extra takes nothing returns nothing
    local boolean transmute = false
    local integer x = 1
    loop
        exitwhen x > udg_total_hero_count
        if udg_hero_category[x] == 11 then
            set transmute = true
        endif
        set x = x + 1
    endloop
    set FF_us_modeExtra = ",pro=" + FF_us_Bit(FFR4Pro or udg_mode_promode) + ",notransmute=" + FF_us_Bit(not transmute) + ",4k=" + FF_us_Bit(FFMode4K)
endfunction

function FF_MM_Init takes nothing returns nothing
    set FF_us_modeHook = CreateTrigger()
    call TriggerAddAction(FF_us_modeHook, function FF_MM_Extra)
endfunction
