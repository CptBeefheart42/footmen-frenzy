-- Engine calls with no behaviour to model (UI, effects, game settings, caches, sounds) that must
-- still hand back an object or a sensible value, because the map uses the result at init.
local W = ...
local H = W.H

function CreateMultiboard() return H("multiboard") end
function MultiboardGetItem() return H("multiboarditem") end
function CreateLeaderboard() return H("leaderboard") end
function CreateQuest() return H("quest") end
function QuestCreateItem() return H("questitem") end
function CreateFogModifierRect() return H("fogmodifier") end
function CreateFogModifierRadius() return H("fogmodifier") end
function CreateTextTag() return H("texttag") end
function AddSpecialEffect() return H("effect") end
function AddSpecialEffectTarget() return H("effect") end
function BlzGetOriginFrame() return H("framehandle") end
function BlzGetFrameByName() return H("framehandle") end
function GetGameSpeed() return MAP_SPEED_FASTEST end
function GetGameDifficulty() return MAP_DIFFICULTY_NORMAL end
function GetResourceDensity() return MAP_DENSITY_MEDIUM end
function GetCreatureDensity() return MAP_DENSITY_MEDIUM end
function GetGameTypeSelected() return GAME_TYPE_USE_MAP_SETTINGS end
function IsGameTypeSupported() return true end
function GetFloatGameState(s) if s == GAME_STATE_TIME_OF_DAY then return 12.0 end return 0.0 end
function GetIntegerGameState() return 0 end
function ReloadGameCachesFromDisk() return false end
function InitGameCache() return H("gamecache") end
function GetSoundDuration() return 0 end
function GetSoundFileDuration() return 0 end
