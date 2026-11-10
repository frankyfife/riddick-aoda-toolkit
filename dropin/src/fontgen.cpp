// Coloured button icons inside the game fonts (port of ../patches/font_color.py).
//
// The fonts carry an A8 atlas (format 0x40000). DXT5 (0x800, the format of the
// button textures in GUI.xtc) needs exactly as many bytes per mip level, so the
// atlas can be rewritten in colour. The icons are the game's own Xbox 360 button
// artwork from GUI.xtc, painted into the largest empty row band of the atlas;
// unused Latin-1 donor characters are pointed at them (msystem.cpp names the pad
// keys with exactly these characters).
#include "common.h"
#include <map>
#include <math.h>
#include <string.h>

static const char kVersion[] = "fontgen 1";

namespace {

struct Img { int w = 0, h = 0; std::vector<float> px; };   // straight RGBA, 0..255

struct Glyph { uint8_t pad, donor; const char* tex; int crop[4]; };   // crop {0} = alpha bounding box
const Glyph kGlyphs[] = {
    { 0xA0, 0xF0, "GUI_Button_A",      {} },
    { 0xA1, 0xF1, "GUI_Button_B",      {} },
    { 0xA2, 0xE6, "GUI_Button_X",      {} },
    { 0xA3, 0xF8, "GUI_Button_Y",      {} },
    { 0xA4, 0xE5, "GUI_Button_Start",  { 29, 20, 82, 63 } },   // without the lettering
    { 0xA5, 0xE3, "GUI_Button_Back",   { 17, 20, 64, 58 } },
    { 0xA6, 0xF5, "GUI_Button_LC",     {} },
    { 0xA7, 0xA1, "GUI_Button_RC",     {} },
    { 0xA8, 0xBF, "GUI_Button_LB",     {} },
    { 0xA9, 0xD0, "GUI_Button_RB",     {} },
    { 0xAA, 0xD1, "GUI_Button_LT",     {} },
    { 0xAB, 0xC6, "GUI_Button_RT",     {} },
    { 0xB0, 0xEC, "GUI_Button_DUp",    {} },
    { 0xB1, 0xED, "GUI_Button_DRight", {} },
    { 0xB2, 0xEE, "GUI_Button_DDown",  {} },
    { 0xB3, 0xEF, "GUI_Button_DLeft",  {} },
};
const int kCellH = 35;   // line height of the fonts
const int kSymH = 31;    // icon height inside the cell
const int kGap = 4;      // multiple of 4, so no DXT block mixes two icons
const uint32_t kFmtDXT5 = 0x800;

uint32_t U32(const std::vector<uint8_t>& d, size_t o) { uint32_t v; memcpy(&v, &d[o], 4); return v; }
// 64-bit range check: offsets come from the file and must not wrap on 32-bit size_t
bool Within(const std::vector<uint8_t>& d, uint64_t off, uint64_t n) { return off + n <= (uint64_t)d.size(); }
void PutU32(std::vector<uint8_t>& d, size_t o, uint32_t v) { memcpy(&d[o], &v, 4); }

// ---- DXT5 --------------------------------------------------------------------------------
void DecodeDXT5(const uint8_t* src, int w, int h, Img& img)
{
    img.w = w; img.h = h; img.px.assign((size_t)w * h * 4, 0);
    for (int by = 0; by < h; by += 4)
        for (int bx = 0; bx < w; bx += 4, src += 16) {
            int a0 = src[0], a1 = src[1], ap[8] = { a0, a1 };
            if (a0 > a1) for (int i = 1; i < 7; ++i) ap[i + 1] = ((7 - i) * a0 + i * a1) / 7;
            else { for (int i = 1; i < 5; ++i) ap[i + 1] = ((5 - i) * a0 + i * a1) / 5; ap[6] = 0; ap[7] = 255; }
            uint64_t ab = 0; for (int i = 0; i < 6; ++i) ab |= (uint64_t)src[2 + i] << (8 * i);
            uint16_t c0 = src[8] | (src[9] << 8), c1 = src[10] | (src[11] << 8);
            uint32_t cb = src[12] | (src[13] << 8) | (src[14] << 16) | ((uint32_t)src[15] << 24);
            auto ex = [](uint16_t c, int* o) { o[0] = ((c >> 11) & 31) * 255 / 31; o[1] = ((c >> 5) & 63) * 255 / 63; o[2] = (c & 31) * 255 / 31; };
            int cp[4][3]; ex(c0, cp[0]); ex(c1, cp[1]);
            for (int k = 0; k < 3; ++k) { cp[2][k] = (2 * cp[0][k] + cp[1][k]) / 3; cp[3][k] = (cp[0][k] + 2 * cp[1][k]) / 3; }
            for (int y = 0; y < 4; ++y) for (int x = 0; x < 4; ++x) {
                if (bx + x >= w || by + y >= h) continue;
                int n = y * 4 + x;
                float* o = &img.px[((size_t)(by + y) * w + bx + x) * 4];
                const int* c = cp[(cb >> (2 * n)) & 3];
                o[0] = (float)c[0]; o[1] = (float)c[1]; o[2] = (float)c[2]; o[3] = (float)ap[(ab >> (3 * n)) & 7];
            }
        }
}

uint16_t To565(const float c[3])
{
    auto q = [](float v, int m) { return (int)lroundf(std::min(255.0f, std::max(0.0f, v)) * m / 255.0f); };
    return (uint16_t)((q(c[0], 31) << 11) | (q(c[1], 63) << 5) | q(c[2], 31));
}

// alpha: 8-value mode; colour: endpoints along the principal axis of the visible pixels
void EncodeDXT5Block(const float (&px)[16][4], uint8_t* o)
{
    int a[16], amax = 0, amin = 255;
    for (int i = 0; i < 16; ++i) { a[i] = (int)lroundf(std::min(255.0f, std::max(0.0f, px[i][3]))); amax = std::max(amax, a[i]); amin = std::min(amin, a[i]); }
    o[0] = (uint8_t)amax; o[1] = (uint8_t)amin;
    uint64_t ab = 0;
    if (amax != amin) {
        int pal[8] = { amax, amin };
        for (int i = 1; i < 7; ++i) pal[i + 1] = ((7 - i) * amax + i * amin) / 7;
        for (int n = 0; n < 16; ++n) {
            int best = 0, bd = 1 << 30;
            for (int k = 0; k < 8; ++k) { int dd = abs(pal[k] - a[n]); if (dd < bd) { bd = dd; best = k; } }
            ab |= (uint64_t)best << (3 * n);
        }
    }
    for (int i = 0; i < 6; ++i) o[2 + i] = (uint8_t)(ab >> (8 * i));
    float mean[3] = {}; int cnt = 0;
    for (int i = 0; i < 16; ++i) if (a[i] > 0) { for (int k = 0; k < 3; ++k) mean[k] += px[i][k]; ++cnt; }
    if (!cnt) {   // fully transparent: keep the colour white like the rest of the atlas
        o[8] = 0xFF; o[9] = 0xFF; o[10] = 0xFF; o[11] = 0xFF; memset(o + 12, 0, 4);
        return;
    }
    for (float& m : mean) m /= cnt;
    float cov[6] = {};
    for (int i = 0; i < 16; ++i) if (a[i] > 0) {
        float d0 = px[i][0] - mean[0], d1 = px[i][1] - mean[1], d2 = px[i][2] - mean[2];
        cov[0] += d0 * d0; cov[1] += d0 * d1; cov[2] += d0 * d2; cov[3] += d1 * d1; cov[4] += d1 * d2; cov[5] += d2 * d2;
    }
    float ax[3] = { 1, 1, 1 };
    for (int it = 0; it < 8; ++it) {
        float n0 = cov[0] * ax[0] + cov[1] * ax[1] + cov[2] * ax[2];
        float n1 = cov[1] * ax[0] + cov[3] * ax[1] + cov[4] * ax[2];
        float n2 = cov[2] * ax[0] + cov[4] * ax[1] + cov[5] * ax[2];
        float l = sqrtf(n0 * n0 + n1 * n1 + n2 * n2);
        if (l < 1e-6f) break;
        ax[0] = n0 / l; ax[1] = n1 / l; ax[2] = n2 / l;
    }
    float tmin = 1e9f, tmax = -1e9f;
    for (int i = 0; i < 16; ++i) if (a[i] > 0) {
        float t = (px[i][0] - mean[0]) * ax[0] + (px[i][1] - mean[1]) * ax[1] + (px[i][2] - mean[2]) * ax[2];
        tmin = std::min(tmin, t); tmax = std::max(tmax, t);
    }
    float e0[3], e1[3];
    for (int k = 0; k < 3; ++k) { e0[k] = mean[k] + ax[k] * tmax; e1[k] = mean[k] + ax[k] * tmin; }
    uint16_t c0 = To565(e0), c1 = To565(e1);
    if (c0 < c1) std::swap(c0, c1);
    uint32_t idx = 0;
    if (c0 != c1) {
        auto ex = [](uint16_t c, float* f) { f[0] = ((c >> 11) & 31) * 255.0f / 31; f[1] = ((c >> 5) & 63) * 255.0f / 63; f[2] = (c & 31) * 255.0f / 31; };
        float pal[4][3]; ex(c0, pal[0]); ex(c1, pal[1]);
        for (int k = 0; k < 3; ++k) { pal[2][k] = (2 * pal[0][k] + pal[1][k]) / 3; pal[3][k] = (pal[0][k] + 2 * pal[1][k]) / 3; }
        for (int n = 0; n < 16; ++n) {
            int best = 0; float bd = 1e30f;
            for (int k = 0; k < 4; ++k) {
                float dd = 0; for (int j = 0; j < 3; ++j) { float t = pal[k][j] - px[n][j]; dd += t * t; }
                if (dd < bd) { bd = dd; best = k; }
            }
            idx |= (uint32_t)best << (2 * n);
        }
    }
    o[8] = (uint8_t)c0; o[9] = (uint8_t)(c0 >> 8); o[10] = (uint8_t)c1; o[11] = (uint8_t)(c1 >> 8);
    memcpy(o + 12, &idx, 4);
}

std::vector<uint8_t> EncodeDXT5(const Img& img)
{
    std::vector<uint8_t> out;
    for (int by = 0; by < img.h; by += 4)
        for (int bx = 0; bx < img.w; bx += 4) {
            float px[16][4];
            for (int y = 0; y < 4; ++y) for (int x = 0; x < 4; ++x) {
                int sx = std::min(bx + x, img.w - 1), sy = std::min(by + y, img.h - 1);
                memcpy(px[y * 4 + x], &img.px[((size_t)sy * img.w + sx) * 4], 16);
            }
            uint8_t blk[16];
            EncodeDXT5Block(px, blk);
            out.insert(out.end(), blk, blk + 16);
        }
    return out;
}

// ---- Lanczos-3 resampling (premultiplied, like Pillow's RGBA resize) ------------------------
double Lanczos(double x)
{
    if (x == 0) return 1;
    if (x <= -3 || x >= 3) return 0;
    double px = 3.14159265358979323846 * x;
    return 3 * sin(px) * sin(px / 3) / (px * px);
}

// one axis: src (n in, stride) -> dst (n out)
void Resample1D(const std::vector<float>& src, int inN, int outN, int lines, bool horiz, int w, std::vector<float>& dst)
{
    double scale = (double)inN / outN, fs = std::max(1.0, scale), support = 3 * fs;
    std::vector<std::vector<std::pair<int, double>>> taps(outN);
    for (int i = 0; i < outN; ++i) {
        double c = (i + 0.5) * scale;
        int lo = std::max(0, (int)(c - support + 0.5)), hi = std::min(inN, (int)(c + support + 0.5));
        double sum = 0;
        for (int j = lo; j < hi; ++j) { double wgt = Lanczos((j - c + 0.5) / fs); taps[i].push_back({ j, wgt }); sum += wgt; }
        if (sum != 0) for (auto& t : taps[i]) t.second /= sum;
    }
    for (int l = 0; l < lines; ++l)
        for (int i = 0; i < outN; ++i) {
            double acc[4] = {};
            for (auto& t : taps[i]) {
                const float* p = horiz ? &src[((size_t)l * inN + t.first) * 4] : &src[((size_t)t.first * w + l) * 4];
                for (int k = 0; k < 4; ++k) acc[k] += p[k] * t.second;
            }
            float* o = horiz ? &dst[((size_t)l * outN + i) * 4] : &dst[((size_t)i * w + l) * 4];
            for (int k = 0; k < 4; ++k) o[k] = (float)acc[k];
        }
}

Img Resize(const Img& s, int w, int h)
{
    std::vector<float> pm(s.px);
    for (size_t i = 0; i < pm.size(); i += 4) { float a = pm[i + 3] / 255.0f; pm[i] *= a; pm[i + 1] *= a; pm[i + 2] *= a; }
    std::vector<float> tmp((size_t)w * s.h * 4), out((size_t)w * h * 4);
    Resample1D(pm, s.w, w, s.h, true, s.w, tmp);
    Resample1D(tmp, s.h, h, w, false, w, out);
    Img d; d.w = w; d.h = h; d.px.swap(out);
    for (size_t i = 0; i < d.px.size(); i += 4) {
        float a = std::min(255.0f, std::max(0.0f, d.px[i + 3]));
        for (int k = 0; k < 3; ++k) d.px[i + k] = a > 0.5f ? std::min(255.0f, std::max(0.0f, d.px[i + k] * 255.0f / a)) : 255.0f;
        d.px[i + 3] = a;
    }
    return d;
}

Img Crop(const Img& s, int x0, int y0, int x1, int y1)
{
    Img d; d.w = x1 - x0; d.h = y1 - y0; d.px.resize((size_t)d.w * d.h * 4);
    for (int y = 0; y < d.h; ++y) memcpy(&d.px[(size_t)y * d.w * 4], &s.px[((size_t)(y + y0) * s.w + x0) * 4], (size_t)d.w * 16);
    return d;
}

Img CropAlphaBox(const Img& s)
{
    int x0 = s.w, y0 = s.h, x1 = -1, y1 = -1;
    for (int y = 0; y < s.h; ++y) for (int x = 0; x < s.w; ++x)
        if (s.px[((size_t)y * s.w + x) * 4 + 3] > 0) { x0 = std::min(x0, x); y0 = std::min(y0, y); x1 = std::max(x1, x); y1 = std::max(y1, y); }
    if (x1 < 0) return s;
    return Crop(s, x0, y0, x1 + 1, y1 + 1);
}

// ---- container --------------------------------------------------------------------------------
struct DirEnt { std::string name; uint32_t slot, next, child, data, len, dim, fmt; };

std::vector<DirEnt> ReadDir(const std::vector<uint8_t>& d)
{
    std::vector<DirEnt> v;
    if (d.size() < 48) return v;
    uint32_t p = U32(d, 24);
    while (Within(d, p, 48)) {
        char nm[25] = {}; memcpy(nm, &d[p], 24);
        if (!nm[0]) break;
        bool ok = true; for (char* c = nm; *c; ++c) if (*c < 32 || *c > 126) ok = false;
        if (!ok) break;
        v.push_back({ nm, p, U32(d, p + 24), U32(d, p + 28), U32(d, p + 32), U32(d, p + 36), U32(d, p + 40), U32(d, p + 44) });
        p += 48;
    }
    return v;
}

// data blocks follow each other, the directory sits at the end, all pointers are
// absolute file offsets: rewrite the whole file and move every pointer
std::vector<uint8_t> Rebuild(const std::vector<uint8_t>& d, const std::map<uint32_t, std::vector<uint8_t>>& newData,
                             const std::map<uint32_t, uint32_t>& newFmt)
{
    auto ents = ReadDir(d);
    uint32_t dirOff = U32(d, 24);
    std::map<uint32_t, uint32_t> lens;
    for (auto& e : ents) if (e.data >= 48) lens[e.data] = std::max(lens[e.data], e.len);
    std::vector<uint8_t> out(d.begin(), d.begin() + 48);
    std::map<uint32_t, uint32_t> remap; remap[0] = 0;
    for (auto& [off, len] : lens) {
        remap[off] = (uint32_t)out.size();
        auto it = newData.find(off);
        if (it != newData.end()) out.insert(out.end(), it->second.begin(), it->second.end());
        else if (off < d.size()) out.insert(out.end(), d.begin() + off, d.begin() + (size_t)std::min<uint64_t>(d.size(), (uint64_t)off + len));
    }
    uint32_t newDir = (uint32_t)out.size();
    int64_t delta = (int64_t)newDir - dirOff;
    for (auto& e : ents) {
        uint8_t rec[48] = {};
        memcpy(rec, e.name.c_str(), std::min<size_t>(24, e.name.size()));
        uint32_t len = e.len;
        auto it = newData.find(e.data);
        if (it != newData.end() && len) len = (uint32_t)it->second.size();
        uint32_t f[6] = { e.next ? (uint32_t)(e.next + delta) : 0, e.child ? (uint32_t)(e.child + delta) : 0,
                          remap.count(e.data) ? remap[e.data] : (uint32_t)(e.data + delta), len, e.dim,
                          newFmt.count(e.slot) ? newFmt.at(e.slot) : e.fmt };
        memcpy(rec + 24, f, 24);
        out.insert(out.end(), rec, rec + 48);
    }
    PutU32(out, 24, newDir);
    return out;
}

bool LoadIcons(std::map<std::string, Img>& out)
{
    std::vector<uint8_t> d;
    if (!ReadFileAll(std::wstring(g_gameRoot) + L"\\Content\\GUI\\Textures\\GUI.xtc", d) || d.size() < 48) { Log("fontgen: GUI.xtc missing"); return false; }
    std::map<std::string, Img> raw;
    for (uint32_t p = U32(d, 24); Within(d, p, 48); p += 48) {
        char nm[25] = {}; memcpy(nm, &d[p], 24);
        const Glyph* g = nullptr;
        for (auto& k : kGlyphs) if (!strcmp(k.tex, nm)) g = &k;
        if (!g || raw.count(nm)) continue;
        uint32_t q = p + 48;
        while (q < p + 48 * 6 && Within(d, q, 48) && memcmp(&d[q], "MIPMAP", 7) != 0) q += 48;
        if (!Within(d, q, 48) || memcmp(&d[q], "MIPMAP", 7) != 0) continue;
        uint32_t dat = U32(d, q + 32);
        if (!Within(d, dat, 36)) continue;
        uint32_t w = U32(d, dat + 12), h = U32(d, dat + 16), fmt = U32(d, dat + 20), use = U32(d, dat + 28);
        if (w == 0 || h == 0 || w > 4096 || h > 4096 || U32(d, dat + 8) < use) continue;
        uint32_t pre = U32(d, dat + 8) - use;
        if (fmt != kFmtDXT5 || use != ((w + 3) / 4) * ((h + 3) / 4) * 16 || !Within(d, (uint64_t)dat + 36 + pre, use)) continue;
        DecodeDXT5(&d[dat + 36 + pre], (int)w, (int)h, raw[nm]);
    }
    for (auto& g : kGlyphs) {
        if (!raw.count(g.tex)) { Log("fontgen: %s not found in GUI.xtc", g.tex); return false; }
        const Img& src = raw[g.tex];
        bool cropOk = g.crop[2] && g.crop[2] <= src.w && g.crop[3] <= src.h && g.crop[0] < g.crop[2] && g.crop[1] < g.crop[3];
        Img im = cropOk ? Crop(src, g.crop[0], g.crop[1], g.crop[2], g.crop[3]) : CropAlphaBox(src);
        int w = std::max(4, (int)lround((double)im.w * kSymH / im.h));
        out[g.tex] = Resize(im, w, kSymH);
    }
    return true;
}

bool BuildFont(std::vector<uint8_t>& d, const std::map<std::string, Img>& icons, const char* name)
{
    auto ents = ReadDir(d);
    const DirEnt* cd = nullptr;
    std::vector<const DirEnt*> mm;
    for (auto& e : ents) {
        if (e.name == "CHARDESC" && !cd) cd = &e;
        if (e.name == "MIPMAP") mm.push_back(&e);
    }
    if (!cd || mm.empty()) { Log("fontgen: %s: no CHARDESC/MIPMAP", name); return false; }
    std::stable_sort(mm.begin(), mm.end(), [](const DirEnt* a, const DirEnt* b) { return a->len > b->len; });
    const DirEnt* big = mm[0];
    for (const DirEnt* e : mm) if (!Within(d, e->data, 36)) { Log("fontgen: %s: MIPMAP outside the file", name); return false; }
    if (!Within(d, cd->data, cd->len)) { Log("fontgen: %s: CHARDESC outside the file", name); return false; }
    int W = (int)U32(d, big->data + 12), H = (int)U32(d, big->data + 16);
    if (W <= 0 || H <= 0 || W > 8192 || H > 8192 || U32(d, big->data + 20) != 0x40000 || !Within(d, (uint64_t)big->data + 36, (uint64_t)W * H)) {
        Log("fontgen: %s: atlas is not A8 (already converted?)", name);
        return false;
    }
    const uint8_t* a8 = &d[big->data + 36];
    Img atlas; atlas.w = W; atlas.h = H; atlas.px.resize((size_t)W * H * 4);
    for (size_t i = 0; i < (size_t)W * H; ++i) { float* p = &atlas.px[i * 4]; p[0] = p[1] = p[2] = 255; p[3] = a8[i]; }

    std::map<uint16_t, int> where;
    int nch = (int)(cd->len / 34);
    for (int i = 0; i < nch; ++i) { uint16_t c; memcpy(&c, &d[cd->data + i * 34 + 32], 2); where[c] = i; }

    // largest band of empty rows
    int bestLo = -1, bestHi = -2, lo = -1;
    for (int y = 0; y <= H; ++y) {
        bool empty = y < H;
        if (empty) for (int x = 0; x < W; ++x) if (a8[(size_t)y * W + x]) { empty = false; break; }
        if (empty) { if (lo < 0) lo = y; }
        else if (lo >= 0) { if (y - 1 - lo > bestHi - bestLo) { bestLo = lo; bestHi = y - 1; } lo = -1; }
    }
    if (bestLo < 0 || bestHi - bestLo + 1 < kCellH + 2 * kGap) { Log("fontgen: %s: not enough free space", name); return false; }

    int y = (bestLo + kGap + 3) & ~3, x = 0, placed = 0;
    for (auto& g : kGlyphs) {
        if (!where.count(g.donor)) { Log("fontgen: %s: donor 0x%02X missing", name, g.donor); continue; }
        const Img& ic = icons.at(g.tex);
        int gw = (ic.w + 3) & ~3;
        if (x + gw > W) { x = 0; y = (y + kCellH + kGap + 3) & ~3; }
        if (y + kCellH > bestHi) { Log("fontgen: %s: out of space at %s", name, g.tex); break; }
        int py = y + (6 + 27) / 2 - kSymH / 2 + 1;
        for (int r = 0; r < ic.h; ++r)
            memcpy(&atlas.px[((size_t)(py + r) * W + x) * 4], &ic.px[(size_t)r * ic.w * 4], (size_t)ic.w * 16);
        uint8_t* e = &d[cd->data + where[g.donor] * 34];
        int16_t oy = -5; memcpy(e + 2, &oy, 2);
        float f[6] = { (float)x / W, (float)y / H, (float)(x + ic.w) / W, (float)(y + kCellH) / H, (float)ic.w, (float)kCellH };
        memcpy(e + 4, f, 24);
        int16_t adv = (int16_t)(ic.w + 2); memcpy(e + 30, &adv, 2);
        x += gw + kGap;
        ++placed;
    }

    // every mip level anew: 36-byte head, 16-byte prefix (4, size, 0, 16), DXT5 blocks
    std::map<uint32_t, std::vector<uint8_t>> newData;
    std::map<uint32_t, uint32_t> newFmt;
    for (const DirEnt* e : mm) {
        int w2 = (int)U32(d, e->data + 12), h2 = (int)U32(d, e->data + 16);
        Img lvl = (w2 == W && h2 == H) ? atlas : Resize(atlas, std::max(1, w2), std::max(1, h2));
        if (w2 < 4 || h2 < 4) lvl = Resize(lvl, 4, 4);
        std::vector<uint8_t> blocks = EncodeDXT5(lvl);
        uint32_t pre[4] = { 4, (uint32_t)blocks.size(), 0, 16 };
        uint32_t head[9] = { 0x400, 0x5000, 16 + (uint32_t)blocks.size(), (uint32_t)w2, (uint32_t)h2, kFmtDXT5, 0, (uint32_t)blocks.size(), 1 };
        std::vector<uint8_t> blk((const uint8_t*)head, (const uint8_t*)head + 36);
        blk.insert(blk.end(), (const uint8_t*)pre, (const uint8_t*)pre + 16);
        blk.insert(blk.end(), blocks.begin(), blocks.end());
        newData[e->data] = std::move(blk);
        newFmt[e->slot] = kFmtDXT5;
    }
    d = Rebuild(d, newData, newFmt);
    Log("fontgen: %s: atlas %dx%d, %d icons in rows %d..%d, %u mip levels as DXT5", name, W, H, placed, bestLo, bestHi, (unsigned)mm.size());
    return placed > 0;
}

} // namespace

// ---- menu hint icons -------------------------------------------------------------------
// The cube menus draw their button hints (*BUTTON_DESCRIPTOR in CubeWnd.xrg) with
// GUI_Button_{A,B,X,Y}_32 at the texture's size, 32x32 on the 640x480 canvas - far
// too big next to a label sized down with "§Z" (datagen.cpp). Those four textures
// are used by the descriptors only, so they are regenerated: the full-colour Xbox 360
// artwork (GUI_Button_A ...; the _32 originals are paler, see FINDINGS.md), scaled
// to HintSize/35 and centred with a transparent margin. Same sizes, so the data is
// replaced in place in a cached copy of GUI.xtc.
static void GuiGen_Run()
{
    if (!g_cfg.xboxPrompts || g_cfg.hintSize <= 0 || g_cfg.hintIconSize >= 32) return;
    std::wstring src = std::wstring(g_gameRoot) + L"\\Content\\GUI\\Textures\\GUI.xtc";
    std::wstring dst = std::wstring(g_cacheDir) + L"\\Content\\GUI\\Textures\\GUI.xtc";
    char ver[64]; sprintf_s(ver, "guigen 2 icon %d", g_cfg.hintIconSize);
    if (!Cache_IsFresh(dst, src, ver)) {
        DWORD t0 = GetTickCount();
        std::vector<uint8_t> d;
        if (!ReadFileAll(src, d) || d.size() < 48) { Log("guigen: GUI.xtc missing"); return; }
        auto ents = ReadDir(d);
        auto find = [&](const char* n) { for (size_t i = 0; i < ents.size(); ++i) if (ents[i].name == n) return (int)i; return -1; };
        static const char* const kPairs[][2] = {
            { "GUI_Button_A_32", "GUI_Button_A" }, { "GUI_Button_B_32", "GUI_Button_B" },
            { "GUI_Button_X_32", "GUI_Button_X" }, { "GUI_Button_Y_32", "GUI_Button_Y" },
        };
        int done = 0;
        for (auto& pr : kPairs) {
            int di = find(pr[0]), si = find(pr[1]);
            if (di < 0 || si < 0) { Log("guigen: %s/%s not found", pr[0], pr[1]); continue; }
            // full-colour artwork: first (largest) MIPMAP behind the source name
            Img art;
            for (int i = si + 1; i < (int)ents.size() && i < si + 6; ++i) {
                if (ents[i].name != "MIPMAP") continue;
                uint32_t dat = ents[i].data;
                if (!Within(d, dat, 36)) break;
                uint32_t w = U32(d, dat + 12), h = U32(d, dat + 16), use = U32(d, dat + 28), size = U32(d, dat + 8);
                uint32_t pre = size - use;
                if (size >= use && w && h && w <= 4096 && h <= 4096 && U32(d, dat + 20) == kFmtDXT5 &&
                    use == ((w + 3) / 4) * ((h + 3) / 4) * 16 && Within(d, (uint64_t)dat + 36 + pre, use))
                    DecodeDXT5(&d[dat + 36 + pre], (int)w, (int)h, art);
                break;
            }
            if (!art.w) { Log("guigen: %s not decodable", pr[1]); continue; }
            Img icon = CropAlphaBox(art);
            int S = g_cfg.hintIconSize;
            int nw = icon.w >= icon.h ? S : std::max(1, (int)lround((double)icon.w * S / icon.h));
            int nh = icon.h >= icon.w ? S : std::max(1, (int)lround((double)icon.h * S / icon.w));
            icon = Resize(icon, nw, nh);
            Img base; base.w = 32; base.h = 32; base.px.assign(32 * 32 * 4, 0);
            for (size_t i = 0; i < base.px.size(); i += 4) base.px[i] = base.px[i + 1] = base.px[i + 2] = 255;
            int ox = (32 - nw) / 2, oy = (32 - nh) / 2;
            for (int r = 0; r < nh; ++r) memcpy(&base.px[((size_t)(oy + r) * 32 + ox) * 4], &icon.px[(size_t)r * nw * 4], (size_t)nw * 16);
            // every mip level of the _32 texture, in place
            int levels = 0;
            for (int i = di + 1; i < (int)ents.size() && i < di + 12; ++i) {
                if (ents[i].name == "PROPERTIES") continue;
                if (ents[i].name != "MIPMAP") break;
                uint32_t dat = ents[i].data;
                if (!Within(d, dat, 36)) break;
                int w = (int)U32(d, dat + 12), h = (int)U32(d, dat + 16);
                uint32_t use = U32(d, dat + 28), size = U32(d, dat + 8);
                if (size < use || w <= 0 || h <= 0 || w > 32 || h > 32) break;
                uint32_t pre = size - use;
                if (U32(d, dat + 20) != kFmtDXT5 || !Within(d, (uint64_t)dat + 36 + pre, use)) break;
                Img lvl = (w == 32 && h == 32) ? base : Resize(base, std::max(1, w), std::max(1, h));
                if (w < 4 || h < 4) lvl = Resize(lvl, 4, 4);
                std::vector<uint8_t> blocks = EncodeDXT5(lvl);
                if (blocks.size() != use) break;
                memcpy(&d[dat + 36 + pre], blocks.data(), use);
                ++levels;
            }
            if (levels) ++done;
            Log("guigen: %s <- %s at %dx%d, %d mip levels", pr[0], pr[1], nw, nh, levels);
        }
        if (!done) return;
        if (!WriteFileAll(dst, d)) { Log("guigen: cannot write %ls", dst.c_str()); return; }
        Cache_Stamp(dst, src, ver);
        Log("guigen: GUI.xtc generated in %lu ms", GetTickCount() - t0);
    }
    Files_AddRedirect("content\\gui\\textures\\gui.xtc", dst);
}

void FontGen_Run()
{
    GuiGen_Run();
    if (!g_cfg.xboxPrompts || !g_cfg.colorIcons) return;
    static const char* const kFonts[] = { "Text.xfc", "Subtitle.xfc", "Headings.xfc" };
    std::map<std::string, Img> icons;
    bool iconsLoaded = false, iconsOk = false;
    std::wstring gui = std::wstring(g_gameRoot) + L"\\Content\\GUI\\Textures\\GUI.xtc";
    for (const char* f : kFonts) {
        std::wstring wf; for (const char* c = f; *c; ++c) wf.push_back((wchar_t)*c);
        std::wstring src = std::wstring(g_gameRoot) + L"\\Content\\Fonts\\" + wf;
        std::wstring dst = std::wstring(g_cacheDir) + L"\\Content\\Fonts\\" + wf;
        std::string key = std::string("content\\fonts\\") + f;
        for (auto& c : key) c = (char)tolower((unsigned char)c);
        // the stamp covers the font and GUI.xtc
        WIN32_FILE_ATTRIBUTE_DATA ga = {};
        GetFileAttributesExW(gui.c_str(), GetFileExInfoStandard, &ga);
        char ver[96]; sprintf_s(ver, "%s gui %lu", kVersion, ga.nFileSizeLow);
        if (!Cache_IsFresh(dst, src, ver)) {
            if (!iconsLoaded) { iconsLoaded = true; iconsOk = LoadIcons(icons); }
            if (!iconsOk) return;
            std::vector<uint8_t> d;
            if (!ReadFileAll(src, d)) { Log("fontgen: cannot read %s", f); continue; }
            DWORD t0 = GetTickCount();
            if (!BuildFont(d, icons, f)) { DeleteFileW(dst.c_str()); continue; }
            if (!WriteFileAll(dst, d)) { Log("fontgen: cannot write %ls", dst.c_str()); continue; }
            Cache_Stamp(dst, src, ver);
            Log("fontgen: %s generated in %lu ms", f, GetTickCount() - t0);
        }
        Files_AddRedirect(key, dst);
    }
}
