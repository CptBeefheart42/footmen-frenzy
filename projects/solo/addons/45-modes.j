// FF addons (Solo map only) — the Solo map's own key of the `modes,` row (16-usage.j): no-pool mode.

function FF_MM_Extra takes nothing returns nothing
    set FF_us_modeExtra = ",nopool=" + FF_us_Bit(udg_mode_no_pool)
endfunction

function FF_MM_Init takes nothing returns nothing
    set FF_us_modeHook = CreateTrigger()
    call TriggerAddAction(FF_us_modeHook, function FF_MM_Extra)
endfunction
