function GTW_Damage takes integer rank returns real
    if rank == 1 then
        return 85.0
    elseif rank == 2 then
        return 120.0
    elseif rank == 3 then
        return 190.0
    elseif rank == 4 then
        return 285.0
    elseif rank == 5 then
        return 375.0
    endif
    return 575.0
endfunction
