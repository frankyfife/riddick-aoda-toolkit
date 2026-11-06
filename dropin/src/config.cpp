#include "common.h"

Config g_cfg;

static wchar_t g_ini[MAX_PATH];

static int GetInt(const wchar_t* sec, const wchar_t* key, int def)
{
    return (int)GetPrivateProfileIntW(sec, key, def, g_ini);
}
static std::wstring GetStr(const wchar_t* sec, const wchar_t* key, const wchar_t* def)
{
    wchar_t b[128];
    GetPrivateProfileStringW(sec, key, def, b, 128, g_ini);
    return b;
}
static float GetFloat(const wchar_t* sec, const wchar_t* key, float def)
{
    std::wstring s = GetStr(sec, key, L"");
    return s.empty() ? def : (float)_wtof(s.c_str());
}

struct PadName { const wchar_t* name; int code; };
static const PadName kPad[] = {
    { L"A", 0xA0 }, { L"B", 0xA1 }, { L"X", 0xA2 }, { L"Y", 0xA3 }, { L"START", 0xA4 }, { L"BACK", 0xA5 },
    { L"L3", 0xA6 }, { L"R3", 0xA7 }, { L"LB", 0xA8 }, { L"RB", 0xA9 }, { L"LT", 0xAA }, { L"RT", 0xAB },
};

void ConfigLoad()
{
    swprintf_s(g_ini, L"%s\\AodaFix.ini", g_dllDir);

    g_cfg.xboxPrompts = GetInt(L"Prompts", L"XboxButtons", 1);
    g_cfg.colorIcons  = GetInt(L"Prompts", L"ColorIcons", 1);
    g_cfg.menuTexts   = GetInt(L"Prompts", L"MenuTexts", 1);
    g_cfg.hintSize    = std::min(35, std::max(0, GetInt(L"Prompts", L"HintSize", 20)));
    g_cfg.hintIconSize = std::min(32, std::max(8, GetInt(L"Prompts", L"HintIconSize", 22)));
    std::wstring hb = GetStr(L"Prompts", L"HelpButton", L"L3");
    g_cfg.helpButton = 0xA6;
    for (auto& p : kPad) if (!_wcsicmp(p.name, hb.c_str())) g_cfg.helpButton = p.code;
    std::wstring mp = GetStr(L"Prompts", L"MainMenu", L"xbox");
    g_cfg.menuPlatform = !_wcsicmp(mp.c_str(), L"pc") ? 0 : !_wcsicmp(mp.c_str(), L"ps3") ? 4
                       : !_wcsicmp(mp.c_str(), L"keep") ? -1 : 3;

    g_cfg.borderless   = GetInt(L"Display", L"Borderless", 1);
    g_cfg.fullViewport = GetInt(L"Display", L"FullViewport", 0);
    g_cfg.modeList     = GetInt(L"Display", L"AllDisplayModes", 1);
    g_cfg.desktopMode  = GetInt(L"Display", L"DesktopResolution", 1);
    std::wstring gr = GetStr(L"Display", L"GammaRamp", L"auto");
    g_cfg.gammaRamp = !_wcsicmp(gr.c_str(), L"auto") ? -1 : _wtoi(gr.c_str()) ? 1 : 0;

    g_cfg.shaderFix = GetInt(L"Renderer", L"ShaderFix", 1);
    std::wstring sm = GetStr(L"Renderer", L"ShaderMode", L"keep");
    g_cfg.shaderMode = !_wcsicmp(sm.c_str(), L"keep") ? -1 : std::min(6, std::max(0, _wtoi(sm.c_str())));

    g_cfg.aimAssist = GetInt(L"Gameplay", L"AimAssist", 0);

    g_cfg.rumble     = GetInt(L"Rumble", L"Enable", 1);
    g_cfg.rumbleGain = std::min(4.0f, std::max(0.0f, GetFloat(L"Rumble", L"Gain", 1.0f)));
    g_cfg.rumbleSwap = GetInt(L"Rumble", L"SwapMotors", 0);
    g_cfg.rumbleLog  = GetInt(L"Rumble", L"Log", 0);

    g_cfg.fileLog = GetInt(L"Debug", L"FileLog", 0);
    g_cfg.textLog = GetInt(L"Debug", L"TextLog", 0);

    Log("config: buttons=%d icons=%d texts=%d help=0x%02X menu=%d | borderless=%d viewport=%d modes=%d desktop=%d gamma=%d | "
        "shaderfix=%d shadermode=%d aimassist=%d | rumble=%d gain=%.2f swap=%d",
        g_cfg.xboxPrompts, g_cfg.colorIcons, g_cfg.menuTexts, g_cfg.helpButton, g_cfg.menuPlatform,
        g_cfg.borderless, g_cfg.fullViewport, g_cfg.modeList, g_cfg.desktopMode, g_cfg.gammaRamp,
        g_cfg.shaderFix, g_cfg.shaderMode, g_cfg.aimAssist, g_cfg.rumble, g_cfg.rumbleGain, g_cfg.rumbleSwap);
}
