// e2e scenario "transmute_destroyed" (main and Solo): a Transmute projectile is in the air when the side of its target
// drops out by losing its base. The script is shared: tests/e2e/addons/transmute (the `include` file).

function FF_E2E_TmCase takes nothing returns string
    return "destroyed"
endfunction
