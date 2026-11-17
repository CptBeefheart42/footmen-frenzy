-- Custom, the host's third button: a second dialog with the custom games. 4K is switched off (project.json
-- settings modes.4k), so it offers only Private / Tournament.
local M = require("modes")
M.boot()
local buttons = M.customButtons()
T.check("Custom offers Private / Tournament only", function()
    T.eq(#buttons, 1, "custom games offered: " .. table.concat(buttons, ", "))
    T.ok(buttons[1] and buttons[1]:find("Private", 1, true), "the first is Private / Tournament")
end)
