function FF_AttachHotkeys takes nothing returns nothing
    if DPS_Panel != null and spellKeysToggle != null then
        call BlzFrameSetParent(spellKeysToggle,DPS_Panel)
        call BlzFrameClearAllPoints(spellKeysToggle)
        call BlzFrameSetPoint(spellKeysToggle,FRAMEPOINT_TOPRIGHT,DPS_Panel,FRAMEPOINT_TOPRIGHT,-0.063,-0.010)
        call BlzFrameSetSize(spellKeysToggle,0.082,0.026)
        call BlzFrameSetVisible(spellKeysToggle,true)
    endif
endfunction
