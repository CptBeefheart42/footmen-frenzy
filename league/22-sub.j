// FF addons — substitutions (799X's -sub, when the map's setting sub.enabled is on): when an observer takes over the
// slot of a player who left, the result file gets `sub,<t>,<slot>,<substitute>`, the roster keeps the player who left,
// and the slot's stats keep counting with state=sub (the substitute plays the slot's units). The map calls
// FF_sub_OnReplace from an anchor hook in its takeover (projects/799x/addons/anchors.txt); a map without -sub never does.

globals
    // the slot an observer now plays, by player id + 1 (13..24)
    integer array FF_sub_slotOf
    // the name of the player who left a substituted slot
    string array FF_sub_origName
    boolean array FF_sub_active
endglobals

// The observer with player id `observerId` (12..23) took over `slot` (1..12); `substitute` is the observer's name.
function FF_sub_OnReplace takes integer slot, integer observerId, string substitute returns nothing
    if slot < 1 or slot > 12 or observerId < 12 or observerId > 23 then
        return
    endif
    if not FF_sub_active[slot] then
        set FF_sub_origName[slot] = udg_orig_player_name[slot]
    endif
    set FF_sub_active[slot] = true
    set FF_sub_slotOf[observerId + 1] = slot
    // the slot was frozen as left when its player went; with a substitute it plays on
    if FF_st_state[slot] == FF_ST_LEFT then
        set FF_st_state[slot] = FF_ST_ALIVE
    endif
    call FF_gr_AddEvent("sub," + FF_Elapsed() + "," + I2S(slot) + "," + FF_Sanitize(substitute))
endfunction
