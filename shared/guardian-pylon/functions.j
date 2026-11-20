function GL_PylonImpact takes unit caster, integer rank, real x, real y returns nothing
    local group enemies = CreateGroup()
    local unit target
    local real damage = 40.0
    if rank == 2 then
        set damage = 70.0
    elseif rank == 3 then
        set damage = 90.0
    elseif rank == 4 then
        set damage = 120.0
    elseif rank == 5 then
        set damage = 140.0
    elseif rank == 6 then
        set damage = 200.0
    endif
    call GroupEnumUnitsInRange(enemies, x, y, GL_PYLON_RADIUS, null)
    loop
        set target = FirstOfGroup(enemies)
        exitwhen target == null
        call GroupRemoveUnit(enemies, target)
        if TFP_LinkEnemy(target, GetOwningPlayer(caster)) then
            call UnitDamageTarget(caster, target, damage, false, false, ATTACK_TYPE_NORMAL, DAMAGE_TYPE_MAGIC, WEAPON_TYPE_WHOKNOWS)
        endif
    endloop
    call DestroyGroup(enemies)
    set enemies = null
endfunction
