#!/usr/bin/env python3
r"""
Riddick-Launcher - Assault on Dark Athena.
Riddick launcher - Assault on Dark Athena.

Vier Reiter / four tabs:
  Spiel / Game        Pfad waehlen, Zustand sehen, starten
  Menue / Menu        PC-Cube oder Xbox-Cube, Zielhilfe, Vibration
  Grafik / Graphics   alles, was die Engine wirklich aus der Environment.cfg liest
  Einbau / Install    Bestandteile ein- und ausbauen, alles zurueck

Die Sprache laesst sich oben rechts umschalten; die Oberflaeche baut sich
danach neu auf. Die Wahl wird zusammen mit dem Spielpfad gemerkt.

Starten:  RiddickLauncher.cmd   (oder diese Datei mit pythonw)
"""

import json
import os
import re
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rmod
import sprachen
from sprachen import T

EINST = os.path.join(os.environ.get("LOCALAPPDATA", "."), "RiddickLauncher")
EINST_DATEI = os.path.join(EINST, "launcher.json")

# (Kennung, Textschluessel, betroffene Dateien)
TEILE = [
    ("kern",    "teil_kern",    "GameClasses, GameWorld, MSystem, CubeWnd, CubeInv0"),
    ("grafik",  "teil_grafik",  "RndrGL.dll"),
    ("schrift", "teil_schrift", "Text.xfc, Subtitle.xfc, Headings.xfc"),
    ("texte",   "teil_texte",   "Frontend_*.txt, StringsX360_*.txt"),
    ("rumble",  "teil_rumble",  "RiddickRumble.dll + .ini"),
]

FARBE = {"eingebaut": "#1a7f37", "original": "#57606a",
         "fremd": "#b35900", "unvollstaendig": "#b35900"}
ZUSTAND_TEXT = {"eingebaut": "z_eingebaut", "original": "z_original",
                "fremd": "z_fremd", "unvollstaendig": "z_unvollstaendig"}


class Launcher(tk.Tk):
    def __init__(self):
        super().__init__()
        self.spiel = None
        self.geometry("980x700")
        self.minsize(880, 600)
        sprachen.setzen(self.einstellung("sprache", "de"))
        self.aufbauen()
        self.laden()

    # ------------------------------------------------------- Einstellungen
    def einstellung(self, name, vorgabe=None):
        try:
            with open(EINST_DATEI, encoding="utf-8") as fh:
                return json.load(fh).get(name, vorgabe)
        except Exception:
            return vorgabe

    def merken(self):
        os.makedirs(EINST, exist_ok=True)
        alt = {}
        try:
            with open(EINST_DATEI, encoding="utf-8") as fh:
                alt = json.load(fh)
        except Exception:
            pass
        if self.spiel:
            alt["exe"] = self.spiel.exe
        alt["sprache"] = sprachen.aktuell()
        with open(EINST_DATEI, "w", encoding="utf-8") as fh:
            json.dump(alt, fh, indent=2)

    # ------------------------------------------------------------- Aufbau
    def aufbauen(self):
        for kind in self.winfo_children():
            kind.destroy()
        self.title(T("titel"))
        self.grafik_vars = {}
        self.erw_vars = {}

        oben = ttk.Frame(self, padding=(10, 8))
        oben.pack(fill="x")
        ttk.Label(oben, text=T("spiel_label")).pack(side="left")
        self.pfad_var = tk.StringVar(value=self.spiel.wurzel if self.spiel else "")
        ttk.Entry(oben, textvariable=self.pfad_var).pack(side="left", fill="x",
                                                        expand=True, padx=6)
        ttk.Button(oben, text=T("durchsuchen"), command=self.waehlen).pack(side="left")
        ttk.Label(oben, text="   " + T("sprache") + ":").pack(side="left")
        self.sprach_var = tk.StringVar(value=sprachen.NAMEN[sprachen.aktuell()])
        box = ttk.Combobox(oben, textvariable=self.sprach_var, state="readonly",
                           width=10, values=[sprachen.NAMEN[k] for k in sprachen.SPRACHEN])
        box.pack(side="left", padx=(4, 0))
        box.bind("<<ComboboxSelected>>", self.sprache_wechseln)

        self.buch = ttk.Notebook(self)
        self.buch.pack(fill="both", expand=True, padx=10, pady=(4, 0))
        self.reiter_spiel()
        self.reiter_menue()
        self.reiter_grafik()
        self.reiter_einbau()

        unten = ttk.Frame(self, padding=(10, 8))
        unten.pack(fill="x")
        self.status = tk.StringVar(value=T("kein_spiel"))
        ttk.Label(unten, textvariable=self.status, foreground="#57606a").pack(side="left")
        ttk.Button(unten, text=T("starten"), command=self.starten).pack(side="right")

    def sprache_wechseln(self, _ereignis=None):
        gewaehlt = self.sprach_var.get()
        for k, name in sprachen.NAMEN.items():
            if name == gewaehlt:
                sprachen.setzen(k)
                break
        self.merken()
        self.aufbauen()
        if self.spiel:
            self.auffrischen()

    # -------------------------------------------------------- Reiter Spiel
    def reiter_spiel(self):
        f = ttk.Frame(self.buch, padding=12)
        self.buch.add(f, text=T("reiter_spiel"))
        ttk.Label(f, text=T("zustand_titel"), font=("", 10, "bold")).pack(anchor="w")
        ttk.Label(f, foreground="#57606a", wraplength=880, justify="left",
                  text=T("zustand_hinweis")).pack(anchor="w", pady=(2, 10))
        rahmen = ttk.Frame(f)
        rahmen.pack(fill="x")
        self.zustand_labels = {}
        for teil, schluessel, dateien in TEILE:
            r = ttk.Frame(rahmen)
            r.pack(fill="x", pady=2)
            ttk.Label(r, text=T(schluessel), width=42, anchor="w").pack(side="left")
            lab = ttk.Label(r, text="-", width=18, anchor="w")
            lab.pack(side="left")
            ttk.Label(r, text=dateien, foreground="#8b949e").pack(side="left")
            self.zustand_labels[teil] = lab
        ttk.Separator(f).pack(fill="x", pady=12)
        self.info = tk.StringVar()
        ttk.Label(f, textvariable=self.info, justify="left",
                  foreground="#57606a").pack(anchor="w")

    # -------------------------------------------------------- Reiter Menue
    def reiter_menue(self):
        f = ttk.Frame(self.buch, padding=12)
        self.buch.add(f, text=T("reiter_menue"))

        ttk.Label(f, text=T("hauptmenue"), font=("", 10, "bold")).pack(anchor="w")
        ttk.Label(f, foreground="#57606a", wraplength=880, justify="left",
                  text=T("hauptmenue_info")).pack(anchor="w", pady=(2, 6))
        self.plat_var = tk.StringVar(value="pc")
        for wert, schluessel in (("pc", "plat_pc"), ("xenon", "plat_xenon"),
                                 ("ps3", "plat_ps3")):
            ttk.Radiobutton(f, text=T(schluessel), value=wert, variable=self.plat_var,
                            command=self.plattform_setzen).pack(anchor="w")

        ttk.Separator(f).pack(fill="x", pady=12)
        ttk.Label(f, text=T("zielhilfe"), font=("", 10, "bold")).pack(anchor="w")
        ttk.Label(f, foreground="#57606a", wraplength=880, justify="left",
                  text=T("zielhilfe_info")).pack(anchor="w", pady=(2, 6))
        self.aim_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(f, text=T("zielhilfe_an"), variable=self.aim_var,
                        command=self.zielhilfe_setzen).pack(anchor="w")

        ttk.Separator(f).pack(fill="x", pady=12)
        ttk.Label(f, text=T("vibration"), font=("", 10, "bold")).pack(anchor="w")
        ttk.Label(f, foreground="#57606a", wraplength=880, justify="left",
                  text=T("vibration_info")).pack(anchor="w", pady=(2, 6))
        r = ttk.Frame(f)
        r.pack(anchor="w")
        ttk.Label(r, text=T("staerke"), width=14, anchor="w").pack(side="left")
        self.gain_var = tk.StringVar(value="1.0")
        ttk.Spinbox(r, from_=0.0, to=4.0, increment=0.1, width=8,
                    textvariable=self.gain_var).pack(side="left")
        self.swap_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(f, text=T("motoren_tauschen"),
                        variable=self.swap_var).pack(anchor="w")
        self.rlog_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(f, text=T("protokoll"), variable=self.rlog_var).pack(anchor="w")
        ttk.Button(f, text=T("vib_sichern"),
                   command=self.rumble_sichern).pack(anchor="w", pady=8)

    # ------------------------------------------------------- Reiter Grafik
    def reiter_grafik(self):
        aussen = ttk.Frame(self.buch)
        self.buch.add(aussen, text=T("reiter_grafik"))
        leinwand = tk.Canvas(aussen, borderwidth=0, highlightthickness=0)
        rolle = ttk.Scrollbar(aussen, orient="vertical", command=leinwand.yview)
        f = ttk.Frame(leinwand, padding=12)
        f.bind("<Configure>",
               lambda e: leinwand.configure(scrollregion=leinwand.bbox("all")))
        leinwand.create_window((0, 0), window=f, anchor="nw")
        leinwand.configure(yscrollcommand=rolle.set)
        leinwand.pack(side="left", fill="both", expand=True)
        rolle.pack(side="right", fill="y")
        for w in (leinwand, f):
            w.bind("<MouseWheel>",
                   lambda e: leinwand.yview_scroll(-int(e.delta / 120), "units"))

        sp = sprachen.aktuell()
        ttk.Label(f, text=T("glsl_titel"), font=("", 10, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 2))
        ttk.Label(f, foreground="#57606a", wraplength=840, justify="left",
                  text=T("glsl_info")).grid(row=1, column=0, columnspan=3,
                                            sticky="w", pady=(0, 4))
        self.glsl_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(f, text=T("glsl_an"), variable=self.glsl_var,
                        command=self.glsl_umschalten).grid(row=2, column=0,
                                                           columnspan=3, sticky="w")
        ttk.Separator(f).grid(row=3, column=0, columnspan=3, sticky="ew", pady=10)

        ttk.Label(f, text=T("aufloesung"), font=("", 10, "bold")).grid(
            row=4, column=0, sticky="w", pady=(0, 2))
        ttk.Label(f, foreground="#57606a", wraplength=840, justify="left",
                  text=T("aufloesung_info")).grid(row=5, column=0, columnspan=3,
                                                  sticky="w", pady=(0, 6))
        r = ttk.Frame(f)
        r.grid(row=6, column=0, columnspan=3, sticky="w", pady=(0, 10))
        self.res_var = tk.StringVar()
        self.hz_var = tk.StringVar()
        self.res_box = ttk.Combobox(r, textvariable=self.res_var, width=16,
                                    state="readonly")
        self.res_box.pack(side="left")
        self.res_box.bind("<<ComboboxSelected>>", lambda e: self.hz_fuellen())
        ttk.Label(r, text=T("bei")).pack(side="left")
        self.hz_box = ttk.Combobox(r, textvariable=self.hz_var, width=8, state="readonly")
        self.hz_box.pack(side="left")
        ttk.Label(r, text="  Hz").pack(side="left")

        zeile = 7
        ttk.Separator(f).grid(row=zeile, column=0, columnspan=3, sticky="ew", pady=8)
        zeile += 1
        ttk.Label(f, text=T("darstellung"), font=("", 10, "bold")).grid(
            row=zeile, column=0, sticky="w", pady=(0, 6))
        zeile += 1
        for key, namen, art, zusatz, wer, vorgabe in rmod.GRAFIK:
            ttk.Label(f, text=namen[sp], width=32, anchor="w").grid(
                row=zeile, column=0, sticky="w", pady=1)
            if art == "schalter":
                v = tk.StringVar(value="0")
                ttk.Checkbutton(f, variable=v, onvalue="1", offvalue="0").grid(
                    row=zeile, column=1, sticky="w")
            elif art == "auswahl":
                v = tk.StringVar()
                box = ttk.Combobox(f, width=14, state="readonly",
                                   values=[b for a, b in zusatz])
                box.grid(row=zeile, column=1, sticky="w")
                v.box = box
            else:
                v = tk.StringVar()
                ttk.Entry(f, textvariable=v, width=16).grid(
                    row=zeile, column=1, sticky="w")
            ttk.Label(f, text="%s   %s %s   %s %s"
                      % (key, T("gelesen_von"), wer, T("vorgabe"), vorgabe),
                      foreground="#8b949e").grid(row=zeile, column=2,
                                                 sticky="w", padx=8)
            self.grafik_vars[key] = (v, art, zusatz)
            zeile += 1

        ttk.Separator(f).grid(row=zeile, column=0, columnspan=3, sticky="ew", pady=8)
        zeile += 1
        ttk.Label(f, text=T("erweitert"), font=("", 10, "bold")).grid(
            row=zeile, column=0, sticky="w")
        zeile += 1
        ttk.Label(f, foreground="#57606a", wraplength=840, justify="left",
                  text=T("erweitert_info")).grid(row=zeile, column=0, columnspan=3,
                                                 sticky="w", pady=(0, 6))
        zeile += 1
        for key, namen, wer, vorgabe in rmod.GRAFIK_ERWEITERT:
            ttk.Label(f, text=namen[sp], width=32, anchor="w").grid(
                row=zeile, column=0, sticky="w", pady=1)
            v = tk.StringVar()
            ttk.Entry(f, textvariable=v, width=16).grid(row=zeile, column=1, sticky="w")
            ttk.Label(f, text="%s   %s%s" % (key, wer,
                  ("   %s %s" % (T("vorgabe"), vorgabe)) if vorgabe else ""),
                  foreground="#8b949e").grid(row=zeile, column=2,
                                             sticky="w", padx=8)
            self.erw_vars[key] = v
            zeile += 1

        knoepfe = ttk.Frame(f)
        knoepfe.grid(row=zeile, column=0, columnspan=3, sticky="w", pady=14)
        ttk.Button(knoepfe, text=T("uebernehmen"),
                   command=self.grafik_speichern).pack(side="left")
        ttk.Button(knoepfe, text=T("neu_einlesen"),
                   command=self.grafik_laden).pack(side="left", padx=6)
        ttk.Button(knoepfe, text=T("cfg_zurueck"),
                   command=self.cfg_zuruecksetzen).pack(side="left")
        self.cfg_info = tk.StringVar()
        ttk.Label(f, textvariable=self.cfg_info, foreground="#8b949e",
                  wraplength=840, justify="left").grid(row=zeile + 1, column=0,
                                                       columnspan=3, sticky="w")

    # ------------------------------------------------------- Reiter Einbau
    def reiter_einbau(self):
        f = ttk.Frame(self.buch, padding=12)
        self.buch.add(f, text=T("reiter_einbau"))
        ttk.Label(f, text=T("bestandteile"), font=("", 10, "bold")).pack(anchor="w")
        ttk.Label(f, foreground="#57606a", wraplength=880, justify="left",
                  text=T("einbau_info")).pack(anchor="w", pady=(2, 10))
        for teil, schluessel, _dateien in TEILE:
            r = ttk.Frame(f)
            r.pack(fill="x", pady=3)
            ttk.Label(r, text=T(schluessel), width=42, anchor="w").pack(side="left")
            ttk.Button(r, text=T("einbauen"), width=12,
                       command=lambda t=teil: self.einbauen(t)).pack(side="left", padx=2)
            ttk.Button(r, text=T("entfernen"), width=12,
                       command=lambda t=teil: self.entfernen(t)).pack(side="left", padx=2)
        ttk.Separator(f).pack(fill="x", pady=14)
        r = ttk.Frame(f)
        r.pack(fill="x")
        ttk.Button(r, text=T("alles_einbauen"),
                   command=self.alles_einbauen).pack(side="left")
        ttk.Button(r, text=T("alles_zurueck"),
                   command=self.alles_zurueck).pack(side="left", padx=8)
        self.bak_info = tk.StringVar()
        ttk.Label(f, textvariable=self.bak_info, foreground="#57606a",
                  justify="left", wraplength=880).pack(anchor="w", pady=12)

    # --------------------------------------------------------------- Logik
    def laden(self):
        pfad = self.einstellung("exe")
        if not pfad or not os.path.exists(pfad):
            for k in (r"D:\Games\The Chronicles of Riddick - Assault on Dark Athena",
                      r"C:\Program Files (x86)\Atari"
                      r"\The Chronicles of Riddick - Assault on Dark Athena"):
                p = os.path.join(k, "System", "Win32_x86", "DarkAthena.exe")
                if os.path.exists(p):
                    pfad = p
                    break
        if pfad and os.path.exists(pfad):
            self.setzen(pfad)

    def waehlen(self):
        p = filedialog.askopenfilename(
            title=T("exe_waehlen"),
            filetypes=[("DarkAthena.exe", "DarkAthena.exe"), (T("alle_dateien"), "*.*")])
        if p:
            self.setzen(p)

    def setzen(self, pfad):
        try:
            self.spiel = rmod.Spiel(pfad)
        except Exception as e:
            messagebox.showerror(T("fehler_pfad"), str(e))
            return
        self.pfad_var.set(self.spiel.wurzel)
        self.merken()
        self.auffrischen()

    def auffrischen(self):
        if not self.spiel:
            return
        s = self.spiel
        for teil, _sch, _d in TEILE:
            try:
                z = s.teil_zustand(teil)
            except Exception:
                z = "fremd"
            lab = self.zustand_labels[teil]
            lab.configure(text=T(ZUSTAND_TEXT.get(z, "z_fremd")),
                          foreground=FARBE.get(z, "#57606a"))
        try:
            self.plat_var.set(s.plattform())
        except Exception:
            pass
        z = s.zielhilfe()
        if z is not None:
            self.aim_var.set(z)
        self.rumble_laden()
        self.res_fuellen()
        self.grafik_laden()
        n = len(s.verz["dateien"]) + len(s.verz["neu"])
        self.bak_info.set(T("sicherungen") % (n, s.bak))
        self.info.set("%-16s%s\n%-16s%s\n%-16s%s"
                      % (T("pfad_wurzel"), s.wurzel,
                         T("pfad_exe"), s.exe,
                         T("pfad_cfg"), s.cfg_pfad()))
        zust = s.glsl_zustand()
        self.glsl_var.set(zust == "gefixt")
        probleme = self.spiel.cfg_probleme()
        if zust == "fremd":
            self.status.set(T("glsl_fremd"))
        elif zust == "original":
            self.status.set(T("glsl_warnung"))
        elif probleme:
            k, w, von, bis = probleme[0]
            self.status.set(T("wert_ausserhalb") % (k, w, von, bis))
        else:
            self.status.set(T("bereit"))

    # ------------------------------------------------------------ Aktionen
    def plattform_setzen(self):
        if not self.spiel:
            return
        try:
            if self.spiel.plattform_setzen(self.plat_var.get()):
                self.status.set(T("menue_umgestellt") % self.plat_var.get().upper())
        except Exception as e:
            messagebox.showerror(T("fehler_menue"), str(e))
        self.auffrischen()

    def zielhilfe_setzen(self):
        if not self.spiel:
            return
        try:
            self.spiel.zielhilfe_setzen(self.aim_var.get())
            self.status.set(T("zielhilfe_status")
                            % (T("an") if self.aim_var.get() else T("aus")))
        except Exception as e:
            messagebox.showerror(T("fehler_zielhilfe"), str(e))
        self.auffrischen()

    def rumble_ini(self):
        return os.path.join(self.spiel.sys, "RiddickRumble.ini")

    def rumble_laden(self):
        p = self.rumble_ini()
        if not os.path.exists(p):
            return
        t = open(p, encoding="latin1").read()

        def hol(k, vorgabe):
            m = re.search(r"(?mi)^%s\s*=\s*([^\r\n;]*)" % k, t)
            return m.group(1).strip() if m else vorgabe
        self.gain_var.set(hol("Gain", "1.0"))
        self.swap_var.set(hol("SwapMotors", "0") == "1")
        self.rlog_var.set(hol("Log", "0") == "1")

    def rumble_sichern(self):
        if not self.spiel:
            return
        p = self.rumble_ini()
        if not os.path.exists(p):
            messagebox.showinfo(T("vibration"), T("vib_fehlt"))
            return
        t = open(p, encoding="latin1").read()
        for k, v in (("Gain", self.gain_var.get()),
                     ("SwapMotors", "1" if self.swap_var.get() else "0"),
                     ("Log", "1" if self.rlog_var.get() else "0")):
            mu = re.compile(r"(?mi)^(%s\s*=).*$" % k)
            if mu.search(t):
                t = mu.sub(lambda m: m.group(1) + v, t)
            else:
                t += "\n%s=%s\n" % (k, v)
        open(p, "w", encoding="latin1", newline="\r\n").write(t)
        self.status.set(T("vib_gesichert"))

    def glsl_umschalten(self):
        if not self.spiel:
            return
        try:
            self.spiel.glsl_setzen(self.glsl_var.get())
        except Exception as e:
            messagebox.showerror(T("glsl_titel"), str(e))
        self.auffrischen()

    # --------------------------------------------------------------- Grafik
    def res_fuellen(self):
        self.modi = rmod.anzeigemodi()
        werte = ["%dx%d" % k for k in sorted(self.modi, key=lambda k: (k[0], k[1]))]
        self.res_box.configure(values=werte)

    def hz_fuellen(self, gewaehlt=None):
        try:
            b, h = (int(x) for x in self.res_var.get().split("x"))
        except Exception:
            return
        hz = [str(x) for x in self.modi.get((b, h), [])]
        self.hz_box.configure(values=hz)
        if gewaehlt and str(gewaehlt) in hz:
            self.hz_var.set(str(gewaehlt))
        elif hz and self.hz_var.get() not in hz:
            self.hz_var.set(hz[0])

    def grafik_laden(self):
        if not self.spiel:
            return
        werte = self.spiel.cfg_lesen()
        teile = werte.get("VID_MODE", "").replace(",", " ").split()
        if len(teile) == 4 and teile[0].isdigit():
            self.res_var.set("%sx%s" % (teile[0], teile[1]))
            self.hz_fuellen(teile[3])
        else:
            b, h, hz = rmod.aktueller_modus()
            self.res_var.set("%dx%d" % (b, h))
            self.hz_fuellen(hz)
        for key, (v, art, zusatz) in self.grafik_vars.items():
            w = werte.get(key, "")
            if art == "auswahl":
                anzeige = dict(zusatz).get(w)
                v.box.set(anzeige if anzeige else (w or ""))
            else:
                v.set(w)
        for key, v in self.erw_vars.items():
            v.set(werte.get(key, ""))
        self.cfg_info.set(T("cfg_gelesen") % self.spiel.cfg_pfad())

    def grafik_speichern(self):
        if not self.spiel:
            return
        aend = {}
        try:
            b, h = (int(x) for x in self.res_var.get().split("x"))
            hz = int(self.hz_var.get())
            aend["VID_MODE"] = "%d %d 32 %d" % (b, h, hz)
            aend["VID_DWIDTH"] = str(b)
            aend["VID_DHEIGHT"] = str(h)
        except Exception:
            pass
        for key, (v, art, zusatz) in self.grafik_vars.items():
            if art == "auswahl":
                anzeige = v.box.get()
                rueck = {b: a for a, b in zusatz}
                if anzeige in rueck:
                    aend[key] = rueck[anzeige]
                elif anzeige:
                    aend[key] = anzeige
            else:
                w = v.get().strip()
                if w != "":
                    aend[key] = w
        for key, v in self.erw_vars.items():
            w = v.get().strip()
            if w != "":
                aend[key] = w
        try:
            self.spiel.cfg_schreiben(aend)
            self.status.set(T("n_geschrieben") % len(aend))
            self.cfg_info.set(T("cfg_geschrieben") % self.spiel.cfg_pfad())
        except Exception as e:
            messagebox.showerror(T("fehler_grafik"), str(e))

    def cfg_zuruecksetzen(self):
        if not self.spiel:
            return
        if self.spiel.cfg_zurueck():
            self.status.set(T("cfg_zurueckgesetzt"))
            self.grafik_laden()
        else:
            messagebox.showinfo(T("fehler_grafik"), T("cfg_keine_sicherung"))

    # --------------------------------------------------------------- Einbau
    def einbauen(self, teil):
        if not self.spiel:
            return
        try:
            n = self.spiel.teil_einbauen(teil)
            self.status.set(T("n_eingebaut") % (teil, n))
        except Exception as e:
            messagebox.showerror(T("fehler_einbau"), str(e))
        self.auffrischen()

    def entfernen(self, teil):
        if not self.spiel:
            return
        try:
            n = self.spiel.teil_entfernen(teil)
            self.status.set(T("n_zurueck") % (teil, n))
        except Exception as e:
            messagebox.showerror(T("fehler_entfernen"), str(e))
        self.auffrischen()

    def alles_einbauen(self):
        if not self.spiel:
            return
        fehler = []
        for teil, _sch, _d in TEILE:
            try:
                self.spiel.teil_einbauen(teil)
            except Exception as e:
                fehler.append("%s: %s" % (teil, e))
        self.auffrischen()
        if fehler:
            messagebox.showwarning(T("fehler_einbau"), "\n\n".join(fehler))
        else:
            self.status.set(T("alles_fertig"))

    def alles_zurueck(self):
        if not self.spiel:
            return
        if not messagebox.askyesno(T("alles_zurueck"), T("frage_zurueck")):
            return
        n = self.spiel.alles_zurueck()
        self.spiel.cfg_zurueck()
        self.auffrischen()
        self.status.set(T("n_zurueckgenommen") % n)

    def starten(self):
        if not self.spiel:
            messagebox.showinfo(T("fehler_start"), T("erst_waehlen"))
            return
        try:
            self.spiel.starten()
        except Exception as e:
            messagebox.showerror(T("fehler_start"), str(e))


if __name__ == "__main__":
    Launcher().mainloop()
