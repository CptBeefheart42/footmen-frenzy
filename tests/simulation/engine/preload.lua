-- Preload files: the way a map writes files to disk (CustomMapData), and so the map's output.
--
-- A map writes a file by collecting strings (Preload) and saving them (PreloadGenEnd). The real
-- client keeps at most 259 characters of each string and silently drops the rest; a longer string
-- is a script error here, stored cut like the game does.
local W = ...

local PRELOAD_MAX = 259

W.files = {}          -- file name -> its strings, as of the latest write
local buffer = nil

function PreloadGenClear() buffer = {} end
function PreloadGenStart() buffer = buffer or {} end
function Preload(s)
    if #s > PRELOAD_MAX then
        W.report("Preload string of " .. #s .. " chars (the game cuts it at " .. PRELOAD_MAX .. "): " .. s:sub(1, 60) .. "...", "Preload")
        s = s:sub(1, PRELOAD_MAX)
    end
    if buffer then buffer[#buffer + 1] = s end
end
function PreloadGenEnd(name)
    W.files[name] = buffer or {}
    buffer = nil
end
function Preloader(name) end
function PreloadStart() end
function PreloadEnd() end
function PreloadRefresh() end
