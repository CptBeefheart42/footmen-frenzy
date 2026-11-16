// FF addons, Solo map only (FF_JASS_MAP_ADDONS) — the camera-zoom slider on WC3 3.0.
//
// The base map's zoom___CreateSlider builds the slider at map init from Blizzard's built-in templates
// (QuestMainListScrollBar / EscMenuLabelTextTemplate / ScriptDialogButton) and loads a
// war3mapImported\templates.toc the map doesn't ship. On 3.0 those templates aren't loaded yet at map
// start, so its slider, label and lock button stay invisible and every player gets a red
// "failed to load templates.toc" line. The build stubs zoom___CreateSlider (SOLO_STUB_FUNCS); this
// creates the same frames shortly after the game starts, from our own copies of those templates
// (imports/war3mapImported/FFZoom.fdf). Everything else — the frame globals, slider/lock handlers, the
// -zoom chat command and the FileIO save — is the base map's own code.
// Frames are created on every client, never inside a GetLocalPlayer block: framehandles are agents
// since 3.0, so creating them locally would desync.

function FF_ZoomSlider_Create takes nothing returns nothing
    local framehandle gameUI = BlzGetOriginFrame(ORIGIN_FRAME_GAME_UI, 0)
    local trigger sliderTrigger = CreateTrigger()
    local trigger lockTrigger = CreateTrigger()
    call DestroyTimer(GetExpiredTimer())
    call BlzLoadTOCFile("war3mapImported\\FFZoom.toc")
    set zoom___slider = BlzCreateFrameByType("SLIDER", "FootmenZoomVertical", gameUI, "FFZoomSlider", 0)
    set zoom___sliderLabel = BlzCreateFrame("FFZoomLabel", zoom___slider, 0, 0)
    call BlzFrameClearAllPoints(zoom___slider)
    call BlzFrameSetAbsPoint(zoom___slider, FRAMEPOINT_CENTER, 0.190, 0.083)
    call BlzFrameSetSize(zoom___slider, 0.009, 0.082)
    call BlzFrameSetAbsPoint(zoom___sliderLabel, FRAMEPOINT_CENTER, 0.190, 0.029)
    call BlzFrameSetTextColor(zoom___sliderLabel, 0xFFFFCC00)
    call BlzFrameSetScale(zoom___sliderLabel, 0.55)
    call BlzFrameSetMinMaxValue(zoom___slider, I2R(zoom___gMinDistance), I2R(zoom___gMaxDistance))
    call BlzFrameSetStepSize(zoom___slider, 100.00)
    call BlzFrameSetEnable(zoom___slider, true)
    call BlzFrameSetVisible(zoom___slider, true)
    set zoom___lockButton = BlzCreateFrame("FFZoomLockButton", gameUI, 0, 0)
    call BlzFrameSetAbsPoint(zoom___lockButton, FRAMEPOINT_CENTER, 0.190, 0.138)
    call BlzFrameSetSize(zoom___lockButton, 0.025, 0.020)
    call BlzFrameSetLevel(zoom___lockButton, 10)
    call BlzFrameSetText(zoom___lockButton, "")
    set zoom___lockLabel = BlzCreateFrameByType("TEXT", "", zoom___lockButton, "", 0)
    call BlzFrameSetAbsPoint(zoom___lockLabel, FRAMEPOINT_CENTER, 0.190, 0.138)
    call BlzFrameSetSize(zoom___lockLabel, 0.010, 0.010)
    call BlzFrameSetTextAlignment(zoom___lockLabel, TEXT_JUSTIFY_MIDDLE, TEXT_JUSTIFY_CENTER)
    call BlzFrameSetScale(zoom___lockLabel, 0.55)
    call BlzFrameSetLevel(zoom___lockLabel, 11)
    call BlzFrameSetText(zoom___lockLabel, "|cffffffffX|r")
    call BlzTriggerRegisterFrameEvent(sliderTrigger, zoom___slider, FRAMEEVENT_SLIDER_VALUE_CHANGED)
    call TriggerAddAction(sliderTrigger, function zoom___handleSlider)
    call BlzTriggerRegisterFrameEvent(lockTrigger, zoom___lockButton, FRAMEEVENT_CONTROL_CLICK)
    call TriggerAddAction(lockTrigger, function zoom___handleLockButton)
    call BlzFrameSetValue(zoom___slider, GetCameraField(CAMERA_FIELD_TARGET_DISTANCE))
    call zoom___UpdateSliderLabel(R2I(GetCameraField(CAMERA_FIELD_TARGET_DISTANCE)))
    call zoom___UpdateLockButton(GetLocalPlayer())
    set gameUI = null
    set sliderTrigger = null
    set lockTrigger = null
endfunction

// Injected by the build runner right after `call FF_Init()` when FF_JASS_MAP_ADDONS is set.
function FF_MapInit takes nothing returns nothing
    call FF_MM_Init()
    call FF_MA_Init()
    call TimerStart(CreateTimer(), 0.25, false, function FF_ZoomSlider_Create)
endfunction
