#include "common.h"
#include <stdarg.h>
#include <string.h>
#include <share.h>

static FILE* g_log;
static CRITICAL_SECTION g_logCs;

void LogInit(const wchar_t* dir)
{
    InitializeCriticalSection(&g_logCs);
    wchar_t path[MAX_PATH];
    swprintf_s(path, L"%s\\AodaFix.log", dir);
    g_log = _wfsopen(path, L"w", _SH_DENYWR);
}

void Log(const char* fmt, ...)
{
    if (!g_log) return;
    EnterCriticalSection(&g_logCs);
    SYSTEMTIME st; GetLocalTime(&st);
    fprintf(g_log, "[%02d:%02d:%02d.%03d] ", st.wHour, st.wMinute, st.wSecond, st.wMilliseconds);
    va_list ap; va_start(ap, fmt); vfprintf(g_log, fmt, ap); va_end(ap);
    fputc('\n', g_log);
    fflush(g_log);
    LeaveCriticalSection(&g_logCs);
}

bool WriteMem(void* dst, const void* src, size_t n)
{
    DWORD old;
    if (!VirtualProtect(dst, n, PAGE_EXECUTE_READWRITE, &old)) return false;
    memcpy(dst, src, n);
    VirtualProtect(dst, n, old, &old);
    FlushInstructionCache(GetCurrentProcess(), dst, n);
    return true;
}

void* PatchIAT(HMODULE module, const char* importDll, const char* func, void* replacement)
{
    if (!module) return nullptr;
    auto base = (uint8_t*)module;
    auto nt = (IMAGE_NT_HEADERS*)(base + ((IMAGE_DOS_HEADER*)base)->e_lfanew);
    auto& dir = nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT];
    if (!dir.VirtualAddress) return nullptr;
    for (auto imp = (IMAGE_IMPORT_DESCRIPTOR*)(base + dir.VirtualAddress); imp->Name; ++imp) {
        if (_stricmp((char*)(base + imp->Name), importDll) != 0) continue;
        // Without a name table (packed modules such as dvm.dll) the IAT already holds
        // bound addresses - they are not name RVAs, so such imports are left alone.
        if (!imp->OriginalFirstThunk) continue;
        auto thunk = (IMAGE_THUNK_DATA*)(base + imp->FirstThunk);
        auto orig = (IMAGE_THUNK_DATA*)(base + imp->OriginalFirstThunk);
        for (; orig->u1.AddressOfData; ++orig, ++thunk) {
            if (IMAGE_SNAP_BY_ORDINAL(orig->u1.Ordinal)) continue;
            if (orig->u1.AddressOfData >= nt->OptionalHeader.SizeOfImage) continue;
            auto ibn = (IMAGE_IMPORT_BY_NAME*)(base + orig->u1.AddressOfData);
            if (strcmp((char*)ibn->Name, func) != 0) continue;
            void* old = (void*)thunk->u1.Function;
            if (old == replacement) return old;
            WriteMem(&thunk->u1.Function, &replacement, sizeof(void*));
            return old;
        }
    }
    return nullptr;
}

static IMAGE_NT_HEADERS* Nt(HMODULE m)
{
    auto base = (uint8_t*)m;
    return (IMAGE_NT_HEADERS*)(base + ((IMAGE_DOS_HEADER*)base)->e_lfanew);
}

uint32_t ImageSize(HMODULE m) { return Nt(m)->OptionalHeader.SizeOfImage; }

// The headers in memory carry the loader's base after relocation; the
// preferred base is what the file says - read it from disk once.
uint32_t PreferredBase(HMODULE m)
{
    wchar_t path[MAX_PATH];
    if (!GetModuleFileNameW(m, path, MAX_PATH)) return 0;
    HANDLE h = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ, nullptr, OPEN_EXISTING, 0, nullptr);
    if (h == INVALID_HANDLE_VALUE) return 0;
    uint8_t hdr[0x400] = {}; DWORD rd = 0;
    ReadFile(h, hdr, sizeof(hdr), &rd, nullptr);
    CloseHandle(h);
    uint32_t e = *(uint32_t*)(hdr + 0x3C);
    if (e + 0x40 > rd) return 0;
    return *(uint32_t*)(hdr + e + 24 + 28);
}

bool InModule(HMODULE m, const void* p, size_t n)
{
    uintptr_t b = (uintptr_t)m, a = (uintptr_t)p;
    return a >= b && a + n <= b + ImageSize(m);
}

uint8_t* RelTarget(uint8_t* at, int opsize)
{
    return at + opsize + 4 + *(int32_t*)(at + opsize);
}

std::vector<uint8_t*> FindAll(HMODULE module, const uint8_t* pat, size_t n, const char* mask)
{
    std::vector<uint8_t*> out;
    auto base = (uint8_t*)module;
    auto nt = Nt(module);
    auto sec = IMAGE_FIRST_SECTION(nt);
    for (int s = 0; s < nt->FileHeader.NumberOfSections; ++s, ++sec) {
        uint8_t* start = base + sec->VirtualAddress;
        size_t len = std::min<size_t>(sec->Misc.VirtualSize, sec->SizeOfRawData ? sec->SizeOfRawData : sec->Misc.VirtualSize);
        if (len < n) continue;
        for (size_t i = 0; i + n <= len; ++i) {
            if (start[i] != pat[0] && !(mask && mask[0] == '?')) continue;
            size_t k = 0;
            for (; k < n; ++k) if (!(mask && mask[k] == '?') && start[i + k] != pat[k]) break;
            if (k == n) out.push_back(start + i);
        }
    }
    return out;
}

std::vector<uint8_t*> FindAllHex(HMODULE module, const char* hex)
{
    std::vector<uint8_t> pat; std::string mask;
    for (const char* p = hex; *p;) {
        while (*p == ' ') ++p;
        if (!*p) break;
        if (p[0] == '?') { pat.push_back(0); mask += '?'; p += (p[1] == '?') ? 2 : 1; }
        else { char b[3] = { p[0], p[1], 0 }; pat.push_back((uint8_t)strtoul(b, nullptr, 16)); mask += 'x'; p += 2; }
    }
    return FindAll(module, pat.data(), pat.size(), mask.c_str());
}

bool ReadFileAll(const std::wstring& p, std::vector<uint8_t>& out)
{
    HANDLE h = CreateFileW(p.c_str(), GENERIC_READ, FILE_SHARE_READ, nullptr, OPEN_EXISTING, 0, nullptr);
    if (h == INVALID_HANDLE_VALUE) return false;
    LARGE_INTEGER sz; GetFileSizeEx(h, &sz);
    out.resize((size_t)sz.QuadPart);
    DWORD rd = 0; BOOL ok = out.empty() ? TRUE : ReadFile(h, out.data(), (DWORD)out.size(), &rd, nullptr);
    CloseHandle(h);
    return ok && rd == out.size();
}

bool WriteFileAll(const std::wstring& p, const std::vector<uint8_t>& data)
{
    // create the folder chain below the cache root
    for (size_t i = wcslen(g_cacheDir) + 1; i < p.size(); ++i)
        if (p[i] == L'\\') CreateDirectoryW(p.substr(0, i).c_str(), nullptr);
    std::wstring tmp = p + L".tmp";
    HANDLE h = CreateFileW(tmp.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_ALWAYS, 0, nullptr);
    if (h == INVALID_HANDLE_VALUE) return false;
    DWORD wr = 0; WriteFile(h, data.data(), (DWORD)data.size(), &wr, nullptr); CloseHandle(h);
    if (wr != data.size()) { DeleteFileW(tmp.c_str()); return false; }
    return MoveFileExW(tmp.c_str(), p.c_str(), MOVEFILE_REPLACE_EXISTING) != 0;
}

static std::string StampText(const std::wstring& src, const char* version)
{
    WIN32_FILE_ATTRIBUTE_DATA fa = {};
    GetFileAttributesExW(src.c_str(), GetFileExInfoStandard, &fa);
    char s[160];
    sprintf_s(s, "%s %lu %lu %lu", version, fa.nFileSizeLow, fa.ftLastWriteTime.dwLowDateTime, fa.ftLastWriteTime.dwHighDateTime);
    return s;
}

bool Cache_IsFresh(const std::wstring& out, const std::wstring& src, const char* version)
{
    std::vector<uint8_t> st;
    if (GetFileAttributesW(out.c_str()) == INVALID_FILE_ATTRIBUTES) return false;
    if (!ReadFileAll(out + L".stamp", st)) return false;
    return std::string(st.begin(), st.end()) == StampText(src, version);
}

void Cache_Stamp(const std::wstring& out, const std::wstring& src, const char* version)
{
    std::string s = StampText(src, version);
    WriteFileAll(out + L".stamp", std::vector<uint8_t>(s.begin(), s.end()));
}
