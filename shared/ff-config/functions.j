function FF_ConfigRead takes boolean keys returns string
    local string data = FileIO_Read(FF_ConfigFile)
    local integer i = 0
    loop
        exitwhen i >= StringLength(data) or SubString(data,i,i+1) == "|"
        set i = i + 1
    endloop
    if i < StringLength(data) then
        if keys then
            return SubString(data,i+1,StringLength(data))
        endif
        return SubString(data,0,i)
    endif
    if keys then
        set data = FileIO_Read("FF799X_Hotkeys.pld")
    else
        set data = FileIO_Read("FFR_Zoom.txt")
    endif
    if data == null then
        return ""
    endif
    return data
endfunction

function FF_ConfigSave takes boolean keys, string value returns nothing
    if keys then
        call FileIO_Write(FF_ConfigFile, FF_ConfigRead(false)+"|"+value)
    else
        call FileIO_Write(FF_ConfigFile, value+"|"+FF_ConfigRead(true))
    endif
endfunction
