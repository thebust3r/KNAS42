"""KNAS look & feel and sound settings.

Builds the colors, names, logos and volume-leveling settings that get added to every KNAS
screen (weather, sports, break, cable box) when it's served. Everything comes from settings.txt
(the setup page writes it), so nothing in the page files has to be edited.
"""
import json, os, re, time

APP = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(APP)
LOGOS = os.path.join(ROOT, "data", "logos")
LOGO_KINDS = ("station", "sports", "cable")
LOGO_TYPES = {b"\x89PNG": ".png", b"\xff\xd8\xff": ".jpg", b"GIF8": ".gif", b"RIFF": ".webp"}


def env(k, d=""):
    return os.environ.get(k, d).strip()


# ---------------------------------------------------------------- color themes
#            sky top    sky middle  sky bottom  panel      edge       accent     text       ticker     logo       band
PRESETS = {
    "classic":  ("#0e0a44", "#5a2f86", "#e07a2a", "#1d3a9e", "#9cb8ff", "#ffd23a", "#ffffff", "#0e1b5c", "#1d3db8", "#e3261b"),
    "midnight": ("#02030a", "#0b1640", "#1b2a6b", "#13245e", "#6f86d6", "#7fd7ff", "#e9f1ff", "#060c26", "#13246b", "#2a7fff"),
    "sunset":   ("#2b0a3d", "#a2305a", "#ff9a3c", "#6b1f52", "#ffb4c8", "#ffd166", "#ffffff", "#3d0d2e", "#a2305a", "#ff5d3c"),
    "ocean":    ("#01243a", "#05607e", "#29b6c9", "#075e7a", "#9be7f2", "#ffe066", "#ffffff", "#023347", "#0a7ea4", "#ff7043"),
    "forest":   ("#07160c", "#1c4b2a", "#5f8f3e", "#1f5a33", "#a8dca0", "#ffd23a", "#ffffff", "#0b2614", "#2d7a43", "#c2410c"),
    "cherry":   ("#1a0005", "#5a0010", "#b3122b", "#7a0f22", "#ffb3c0", "#ffe08a", "#ffffff", "#2a0008", "#9e1630", "#1d1d1d"),
    "amber":    ("#000000", "#120800", "#2a1400", "#1a0d00", "#ffb000", "#ffb000", "#ffd27a", "#0d0600", "#3a1d00", "#ffb000"),
    "terminal": ("#000000", "#001a06", "#00320c", "#00240a", "#33ff66", "#66ff88", "#c8ffd4", "#000d03", "#003310", "#1fbf4a"),
    "mono":     ("#0a0a0a", "#2a2a2a", "#5a5a5a", "#333333", "#cccccc", "#ffffff", "#ffffff", "#111111", "#444444", "#cc0000"),
    "pastel":   ("#3b3f8f", "#8f6fc2", "#f2a7c3", "#5d5fb3", "#e3dcff", "#fff2a8", "#ffffff", "#2f3170", "#6d6fd0", "#ff7aa8"),
}
COLOR_KEYS = ("COLOR_SKY_TOP", "COLOR_SKY_MIDDLE", "COLOR_SKY_BOTTOM", "COLOR_PANEL", "COLOR_EDGE", "COLOR_ACCENT",
              "COLOR_TEXT", "COLOR_TICKER", "COLOR_LOGO", "COLOR_LOGO_BAND")


def _hex(c, fallback):
    c = (c or "").strip()
    if re.fullmatch(r"#?[0-9a-fA-F]{6}", c):
        return "#" + c.lstrip("#").lower()
    if re.fullmatch(r"#?[0-9a-fA-F]{3}", c):
        c = c.lstrip("#")
        return "#" + "".join(ch * 2 for ch in c).lower()
    return fallback


def _mix(c, other, amt):
    """amt 0..1 of the way from color c to color other"""
    a = [int(c[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(other[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * amt):02x}" for x, y in zip(a, b))


def light(c, amt):
    return _mix(c, "#ffffff", amt)


def dark(c, amt):
    return _mix(c, "#000000", amt)


def colors():
    base = PRESETS.get(env("THEME", "classic").lower(), PRESETS["classic"])
    return [_hex(env(k), base[i]) for i, k in enumerate(COLOR_KEYS)]


def theme_css(page):
    """CSS added to a page so it uses your colors. Classic with no changes adds nothing."""
    custom = any(env(k) for k in COLOR_KEYS)
    scan = env("SCANLINES", "on").lower()
    if env("THEME", "classic").lower() == "classic" and not custom and scan == "on":
        return ""
    s1, s2, s3, panel, edge, accent, text, ticker, logo, band = colors()
    css = []
    css.append(f":root{{--gold:{accent};--gold2:{dark(accent, .25)};--edge:{edge};--panel-edge:{edge};"
               f"--panel-top:{light(panel, .22)};--panel-bot:{dark(panel, .35)};--ice:{_mix(text, edge, .5)};--white:{text};--navy:{dark(panel, .6)}}}")
    css.append(f"body{{color:{text}}}")
    panel_bg = f"linear-gradient(180deg,{light(panel, .22)},{panel} 50%,{dark(panel, .35)})"
    panel_sh = f"inset 0 0 0 3px {edge},inset 0 0 0 5px {dark(panel, .6)},4px 5px 0 rgba(0,0,0,.55)"
    logo_bg = f"linear-gradient(160deg,{light(logo, .35)},{logo} 55%,{dark(logo, .45)})"
    if page != "tv":
        css.append(f"#stage{{background:linear-gradient(180deg,{s1} 0%,{s2} 55%,{s3} 100%)!important}}")
        css.append(f"footer{{background:linear-gradient(180deg,{light(ticker, .12)},{ticker})!important;box-shadow:inset 0 3px 0 {accent},inset 0 5px 0 {dark(accent, .55)}!important}}")
        css.append(f".crawl b,.title .t2,.clock .dt{{color:{accent}}}")
    if page in ("index", "break"):
        sel = "#panel" if page == "index" else ".panel"
        css.append(f"{sel}{{background:{panel_bg}!important;box-shadow:{panel_sh}!important}}")
        css.append(f".logo{{background:{logo_bg}!important;box-shadow:inset 0 0 0 3px {light(logo, .7)},inset 0 0 0 5px {dark(logo, .6)},3px 3px 0 #000!important}}")
        css.append(f".logo .call{{background:{band}!important;box-shadow:0 2px 0 {dark(band, .5)}!important}}")
    if page == "sports":
        css.append(f".panel,.mid,.cd div{{background:{panel_bg}!important}}")
        css.append(f".panel{{box-shadow:{panel_sh}!important}}")
        css.append(f".st-logo{{background:{logo_bg}!important}}.st-logo b{{background:{band}!important}}")
    if page == "tv":
        css.append(f"#banner,#gInfo,#msg{{background:{panel_bg}!important;box-shadow:{panel_sh}!important}}")
        css.append(f".b-num{{background:{logo_bg}!important}}.b-num span{{background:{band}!important}}")
        css.append(f"#gGrid{{background:linear-gradient(180deg,{dark(panel, .15)},{dark(panel, .45)})!important;box-shadow:inset 0 3px 0 {accent},inset 0 5px 0 {dark(accent, .55)}!important}}")
        css.append(f".gh{{background:{dark(panel, .6)}!important}}.gh .gc0,.gh .gs span{{color:{accent}!important}}")
        css.append(f".gr .gcn{{background:linear-gradient(180deg,{light(panel, .15)},{dark(panel, .1)})!important}}.gr .gcn b{{color:{accent}}}")
        css.append(f".cell{{background:linear-gradient(180deg,{light(panel, .08)},{dark(panel, .15)})!important}}")
        css.append(f".cell.now{{background:linear-gradient(180deg,{light(panel, .2)},{panel})!important}}")
        css.append(f".cell.sel{{background:linear-gradient(180deg,{light(accent, .5)},{accent} 45%,{dark(accent, .15)})!important}}")
        css.append(f".gr.cur .gcn{{background:linear-gradient(180deg,{band},{dark(band, .3)})!important}}")
        css.append(f"#gLogo .gl2{{background:linear-gradient(180deg,{light(accent, .6)},{accent} 45%,{dark(accent, .2)})!important;-webkit-background-clip:text!important;background-clip:text!important}}")
    if scan == "off":
        css.append("#stage:before{display:none!important}")
    elif scan == "strong":
        css.append("#stage:before{background:repeating-linear-gradient(0deg,rgba(0,0,0,.22) 0 2px,transparent 2px 4px)!important}")
    return "\n".join(css)


# ---------------------------------------------------------------- guide styles (cable box guide + channel banner)
# Looks inspired by 2000s satellite and cable boxes (no real company names or logos).
_NOITAL = "#guide *,#banner *,#osd{font-style:normal!important}"
GUIDE_STYLES = {
    "knas": "",
    "satellite": _NOITAL + """
#guide,#banner,#osd{font-family:"Trebuchet MS",Verdana,"DejaVu Sans",Arial,sans-serif!important}
#guide *,#banner *{text-shadow:none!important}
#gLogo{border-radius:4px;box-shadow:0 0 0 3px #7fb2ff,0 0 0 3000px #00143a!important;justify-content:flex-end;background:transparent}
#gLogo .gl1,#gLogo .gl2{display:none!important}
#gLogo .gl3{margin:0;font-size:18px;font-weight:700;background:linear-gradient(180deg,rgba(10,40,110,.9),rgba(0,20,60,.9));color:#fff;padding:2px 8px;border-radius:0 0 3px 3px}
#gInfo{background:linear-gradient(180deg,#123e8c,#06225a)!important;border-radius:8px!important;box-shadow:inset 0 0 0 2px #4f8fe6,inset 0 18px 18px rgba(255,255,255,.08)!important}
#gInfo .gt{color:#fff;font-weight:700}#gInfo .gm{color:#8fd8ff!important;font-weight:700}#gInfo .gd{color:#d6e6ff;font-weight:400}
#gGrid{background:#00143a!important;box-shadow:none!important}
.gh{background:linear-gradient(180deg,#3a6fd0,#1b479e)!important;border-radius:4px 4px 0 0}
.gh .gc0,.gh .gs span{color:#fff!important;font-weight:700}.gh .gs span{border-left:1px solid rgba(255,255,255,.45)!important}
.gr{border-bottom:3px solid #00143a!important}
.gr .gcn{background:linear-gradient(180deg,#2f63c4,#173f8f)!important;border-right:3px solid #00143a!important;border-radius:3px 0 0 3px}
.gr .gcn b{color:#fff!important;font-weight:700}.gr .gcn span{color:#cfe2ff;font-weight:700}
.cell{background:linear-gradient(180deg,#2a57ad,#183f86)!important;border-right:3px solid #00143a!important;color:#fff;font-weight:600;border-radius:3px}
.cell.now{background:linear-gradient(180deg,#3366c2,#1d4a9b)!important}
.cell.sel{background:linear-gradient(180deg,#8ff0ff,#25b8e8 55%,#1793c4)!important;color:#00203a!important}
.cell .ar{color:#8fd8ff!important}
.gr.cur .gcn{background:linear-gradient(180deg,#ffb84d,#e07800)!important}.gr.cur .gcn b{color:#fff!important}
#gCur{animation:none!important;box-shadow:0 0 0 3px #fff!important;border-radius:4px}
.gnow{background:rgba(255,255,255,.45)!important;box-shadow:none!important}
#banner{background:linear-gradient(180deg,#123e8c,#06225a)!important;border-radius:10px!important;box-shadow:inset 0 0 0 2px #4f8fe6,inset 0 20px 20px rgba(255,255,255,.08),0 4px 12px rgba(0,0,0,.6)!important}
.b-num{background:transparent!important;box-shadow:none!important}.b-num b{color:#fff;font-weight:700}
.b-num span{background:linear-gradient(180deg,#8ff0ff,#25b8e8)!important;color:#00203a!important;box-shadow:none!important}
.b-title{font-weight:700}.b-sub{color:#8fd8ff!important}.b-next b{color:#8fd8ff!important}
.b-bar{background:#00143a!important;box-shadow:inset 0 0 0 2px #4f8fe6!important;border-radius:6px!important}
.b-bar i{background:linear-gradient(180deg,#8ff0ff,#25b8e8)!important;border-radius:6px}
#osd{color:#fff!important;font-weight:700}""",
    "cable": _NOITAL + """
#guide,#banner,#osd{font-family:Arial,Helvetica,"Liberation Sans",sans-serif!important}
#guide *,#banner *{text-shadow:none!important}
#gLogo{box-shadow:0 0 0 2px #9a9a9a,0 0 0 3000px #121212!important;justify-content:flex-end}
#gLogo .gl1,#gLogo .gl2{display:none!important}
#gLogo .gl3{margin:0;font-size:18px;font-weight:700;background:rgba(0,0,0,.75);color:#ffd400;padding:2px 8px}
#gInfo{background:#1c1c1c!important;border-radius:0!important;box-shadow:inset 0 0 0 2px #555!important}
#gInfo .gt{color:#fff;font-weight:700}#gInfo .gm{color:#ffd400!important}#gInfo .gd{color:#ddd;font-weight:400}
#gGrid{background:#121212!important;box-shadow:inset 0 3px 0 #ffd400!important}
.gh{background:#2e2e2e!important}.gh .gc0,.gh .gs span{color:#ffd400!important;font-weight:700}.gh .gs span{border-left:1px solid #666!important}
.gr{border-bottom:2px solid #121212!important}
.gr .gcn{background:linear-gradient(180deg,#5c5c5c,#3a3a3a)!important;border-right:2px solid #121212!important}
.gr .gcn b{color:#fff!important;font-weight:700}.gr .gcn span{color:#ddd;font-weight:700}
.cell{background:linear-gradient(180deg,#404040,#2b2b2b)!important;border-right:2px solid #121212!important;color:#eee;font-weight:600}
.cell.now{background:linear-gradient(180deg,#4d4d4d,#353535)!important}
.cell.sel{background:#ffd400!important;color:#000!important}
.cell .ar{color:#ffd400!important}.cell.sel .ar{color:#000!important}
.gr.cur .gcn{background:linear-gradient(180deg,#d40000,#8a0000)!important}
#gCur{animation:none!important;box-shadow:0 0 0 2px #fff!important;border-radius:0}
.gnow{background:rgba(255,255,255,.45)!important;box-shadow:none!important}
#banner{background:rgba(18,18,18,.94)!important;border-radius:0!important;box-shadow:inset 0 3px 0 #ffd400,0 0 0 1px #444!important}
.b-num{background:#333!important;border-radius:0!important;box-shadow:inset 0 0 0 2px #666!important}.b-num b{color:#ffd400;font-weight:700}
.b-num span{background:#d40000!important;box-shadow:none!important}
.b-title{font-weight:700}.b-sub{color:#bbb!important}.b-next b{color:#ffd400!important}
.b-bar{background:#000!important;box-shadow:inset 0 0 0 1px #777!important;border-radius:0!important}.b-bar i{background:#ffd400!important}
#osd{color:#ffd400!important;font-weight:700}""",
    "chrome": _NOITAL + """
#guide,#banner,#osd{font-family:Verdana,Tahoma,"DejaVu Sans",Arial,sans-serif!important}
#guide *,#banner *{text-shadow:none!important}
#gLogo{border-radius:10px;box-shadow:0 0 0 3px #e8edf4,0 0 0 5px #6b7a92,0 0 0 3000px #26344c!important;justify-content:flex-end}
#gLogo .gl1,#gLogo .gl2{display:none!important}
#gLogo .gl3{margin:0;font-size:16px;font-weight:700;background:linear-gradient(180deg,#f5f8fc,#b8c3d3);color:#13294a;padding:2px 8px;border-radius:0 0 8px 8px}
#gInfo{background:linear-gradient(180deg,#fbfcfe,#c4cddb)!important;color:#10233f!important;border-radius:12px!important;box-shadow:inset 0 1px 0 #fff,0 0 0 2px #7d8aa0,0 3px 8px rgba(0,0,0,.5)!important}
#gInfo .gt{color:#0f2a55;font-weight:700}#gInfo .gm{color:#0a6fa8!important}#gInfo .gd{color:#24354f;font-weight:400}
#gGrid{background:linear-gradient(180deg,#3a4a66,#26344c)!important;box-shadow:none!important}
.gh{background:linear-gradient(180deg,#e9eef5,#a9b5c7)!important;border-radius:8px 8px 0 0}.gh .gc0,.gh .gs span{color:#13294a!important;font-weight:700}.gh .gs span{border-left:1px solid #7d8aa0!important}
.gr{border-bottom:2px solid #26344c!important}
.gr .gcn{background:linear-gradient(180deg,#f2f5f9,#aeb9ca)!important;border-right:2px solid #26344c!important}
.gr .gcn b{color:#123a73!important;font-weight:700}.gr .gcn span{color:#1a2a44;font-weight:700}
.cell{background:linear-gradient(180deg,#ffffff,#cdd5e0)!important;border-right:2px solid #26344c!important;color:#13223a;font-weight:600}
.cell.now{background:linear-gradient(180deg,#ffffff,#dde4ee)!important}
.cell.sel{background:linear-gradient(180deg,#c8f6ff,#3cc3ee 55%,#1a9fd0)!important;color:#002b40!important}
.cell .ar{color:#1a6fb0!important}
.gr.cur .gcn{background:linear-gradient(180deg,#9fe7ff,#2aa8db)!important}.gr.cur .gcn b{color:#002b40!important}
#gCur{animation:none!important;box-shadow:0 0 0 3px #ff9a00!important;border-radius:6px}
.gnow{background:rgba(255,255,255,.45)!important;box-shadow:none!important}
#banner{background:linear-gradient(180deg,#fbfcfe,#c4cddb)!important;color:#10233f!important;border-radius:14px!important;box-shadow:inset 0 1px 0 #fff,0 0 0 2px #7d8aa0,0 4px 12px rgba(0,0,0,.55)!important}
.b-num{background:linear-gradient(180deg,#5aa9ff,#1c5fc4)!important;border-radius:12px!important;box-shadow:inset 0 1px 0 rgba(255,255,255,.6)!important}
.b-num span{background:#ff7a00!important;box-shadow:none!important}
.b-title{color:#0f2a55;font-weight:700}.b-sub{color:#2c5a8a!important}.b-row,.b-next{color:#1a2a44}.b-next b{color:#0a6fa8!important}.b-clock{color:#fff}
.b-bar{background:#e6ebf2!important;box-shadow:inset 0 0 0 1px #7d8aa0!important;border-radius:8px!important}.b-bar i{background:linear-gradient(180deg,#9fe7ff,#2aa8db)!important;border-radius:8px}
#osd{color:#fff!important;font-weight:700}""",
    "listings": _NOITAL + """
#guide,#banner,#osd{font-family:"Arial Rounded MT Bold","Helvetica Rounded",Arial,Helvetica,"Liberation Sans",sans-serif!important}
#guide *,#banner *{text-shadow:2px 2px 1px rgba(0,0,0,.75)}
#guide.on #gLogo,#guide.on #gInfo,#guide.on #gGrid{animation:none!important}
#gLogo{left:auto!important;right:0!important;top:0!important;width:320px!important;height:182px!important;justify-content:flex-end;background:transparent;
  box-shadow:0 0 0 3000px #8f949b,inset 0 0 0 3px #8f949b!important}
#gLogo .gl1,#gLogo .gl2,#gLogo .gl3{display:none!important}
#gHead{display:flex!important;position:absolute;left:0;top:0;right:320px;height:58px;align-items:center;padding:0 8px 0 14px;
  background:linear-gradient(180deg,#22407a,#1a3366);border-bottom:3px solid #8f949b}
#gHead>*+*{margin-left:10px}
#gHead .gh1{flex:1;min-width:0;font:700 30px/1 Arial,Helvetica,sans-serif!important;color:#c9ced8;letter-spacing:-1px;text-shadow:none!important;white-space:nowrap;overflow:hidden}
#gHead .gh1 img{height:44px;width:auto;max-width:100%;display:block}
#gHead .gh2{display:flex;flex-direction:column;align-items:flex-end;line-height:1.02}
#gHead .gh2 b{font-size:20px;color:#f6e95e}#gHead .gh2 span{font-size:20px;color:#fff}
#gHead .gh3{background:#e32420;color:#fff;font-weight:800;font-size:17px;line-height:.98;text-align:center;padding:5px 7px;border-radius:5px;text-shadow:none!important;text-transform:uppercase;box-shadow:inset 0 0 0 2px rgba(255,255,255,.35)}
#gInfo{left:0!important;top:61px!important;right:320px!important;height:121px!important;border-radius:0!important;padding:6px 12px 6px 14px!important;
  background:linear-gradient(180deg,#24467f 0%,#3a609c 55%,#7d9bcb 100%)!important;box-shadow:none!important}
#gInfo .swap{animation:none!important}
#gInfo .gch{float:right;margin-left:10px;font-size:20px;font-weight:700;color:#fff;text-align:right;line-height:1.1}
#gInfo .gch .rt{display:block;margin:3px 0 0 auto;width:max-content;font-size:13px;padding:1px 5px;border-radius:3px;background:#fff;color:#14244a;text-shadow:none!important}
#gInfo .gt{font-size:22px!important;color:#f6e95e;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;display:block!important}
#gInfo .gtm{font-size:19px;color:#fff;font-weight:700;margin:1px 0 2px}
#gInfo .gd{font-size:18px!important;color:#fff;font-weight:700;line-height:1.12;-webkit-line-clamp:3!important}
#gInfo .gimg{display:none!important}
#gGrid{top:182px!important;background:#8f949b!important;box-shadow:none!important}
.gh{top:0!important;height:39px!important;background:linear-gradient(180deg,#1d3a72,#152c5c)!important;border-bottom:3px solid #0b0d12;box-sizing:border-box}
.gh .gc0{font-size:21px!important;color:#fff!important;font-weight:700;padding:6px 10px!important;text-align:right}
.gh .gc0:after{content:" ◀";font-size:17px}
.gh .gs:after{content:"▶";position:absolute;right:8px;top:6px;font-size:19px;color:#fff}
.gh .gs span{color:#fff!important;font-weight:700;font-size:21px!important;top:5px!important;border-left:3px solid #3f6fcf!important;padding-left:12px!important}
.grows{top:39px!important}
.gr{border-bottom:3px solid #8f949b!important}
#guide .gr .gcn{background:#9cc0e8!important;background-image:none!important;border-right:5px solid #0b0d12!important;box-shadow:0 3px 0 #0b0d12}
#guide .gr .gcn>*+*{margin-left:6px!important}
#guide .gr .gcn b,#guide .gr .gcn span,#guide .gr.cur .gcn b,#guide .gr.cur .gcn span{color:#10203d!important;text-shadow:none!important;font-style:normal!important;font-weight:700!important}
.gr .gcn b{font-size:22px!important;min-width:0!important}
.gr .gcn span{font-size:20px!important;-webkit-line-clamp:1!important;white-space:nowrap;text-overflow:ellipsis}
#guide .gr.cur .gcn,#guide .gr.cur .gcn:before{background:#c9def6!important;background-image:none!important}
#guide .cell{background:#1e3c78!important;background-image:none!important;border-right:3px solid #8f949b!important;box-shadow:none!important;color:#fff;font-weight:700;font-size:21px!important;padding:0 10px!important}
#guide .cell.now{background:#1e3c78!important}
#guide .cell.k-sports{background:#127a3b!important}
#guide .cell.k-movie{background:#5a2a8c!important}
#guide .cell.k-kids{background:#93b8e3!important}
#guide .cell.sel{background:#f9f29c!important;color:#1a1a1a!important}.cell.sel *{text-shadow:none!important}
.cell.two .ct,.cell.two.tiny .ct{white-space:nowrap!important;display:block!important;font-size:inherit!important;line-height:1.08!important;text-overflow:ellipsis!important}
#guide .cell .ar{display:none!important}
#gCur{animation:none!important;box-shadow:none!important}
.gnow{display:none!important}
#banner{background:linear-gradient(180deg,#24467f 0%,#3a609c 60%,#7d9bcb 100%)!important;border-radius:0!important;box-shadow:0 0 0 3px #8f949b,0 4px 12px rgba(0,0,0,.6)!important}
.b-num{background:#9cc0e8!important;border-radius:0!important;box-shadow:none!important}.b-num b{color:#10203d!important;text-shadow:none!important}
.b-num span{background:#e32420!important;box-shadow:none!important}
.b-title{color:#f6e95e!important;font-weight:700}.b-sub{color:#fff!important}.b-next b{color:#f6e95e!important}
.b-bar{background:#152c5c!important;box-shadow:inset 0 0 0 2px #8f949b!important;border-radius:0!important}.b-bar i{background:#f9f29c!important}
#osd{color:#fff!important;font-weight:700}""",
}
GUIDE_PIP = ("satellite", "cable", "chrome", "listings")     # these show the live picture in a little window


def guide_style():
    g = env("GUIDE_STYLE", "knas").lower()
    return g if g in GUIDE_STYLES else "knas"


# ---------------------------------------------------------------- fonts
# All fonts are free (SIL Open Font License) and stored in web/fonts, so they load fast and work
# with no internet. Every page asks for "Barlow Condensed"; the chosen font is loaded under that
# name, so changing the font never needs the page files edited.
#   key: (name on the setup page, description, file prefix, weights, italic weights, size-adjust %)
# size-adjust makes wider fonts a bit smaller so words still fit in the same space.
W5 = (400, 500, 600, 700, 800)
I3 = (600, 700, 800)
FONTS = {
    # Clean & easy to read
    "classic":    ("Classic", "Bold and condensed, the original KNAS look", "classic", W5, I3, 100, "Clean & easy to read"),
    "smooth":     ("Smooth", "Softer curves, very easy to read on a TV", "smooth", W5, I3, 92, "Clean & easy to read"),
    "modern":     ("Modern News", "Clean, like today's news graphics", "modern", W5, I3, 93, "Clean & easy to read"),
    "easyread":   ("Easy Read", "Wide and open, made for easy reading", "easyread", W5, (), 78, "Clean & easy to read"),
    "rounded":    ("Rounded", "Soft round letters, friendly and clear", "rounded", W5, I3, 82, "Clean & easy to read"),
    # Bold & sporty
    "headline":   ("Headline", "Tall and punchy, like a newspaper headline", "headline", (400, 500, 600, 700), (), 90, "Bold & sporty"),
    "scoreboard": ("Scoreboard", "Squared-off and sporty", "scoreboard", W5, (), 100, "Bold & sporty"),
    "jersey":     ("Jersey", "All capitals, tall like a team jersey", "jersey", (400,), (), 104, "Bold & sporty"),
    "friendly":   ("Friendly", "Condensed with rounded corners", "friendly", W5, I3, 100, "Bold & sporty"),
    # Retro
    "y2k":        ("Y2K", "Techy and futuristic, very year 2000", "y2k", W5, I3, 82, "Retro"),
    "neon":       ("Neon Diner", "80s and 90s sign lettering", "neon", (400,), (), 82, "Retro"),
    "teletext":   ("Teletext", "Pixel letters like an old computer screen", "teletext", (400,), (), 104, "Retro"),
    "computer":   ("Typewriter", "Every letter the same width, like a terminal", "computer", (400, 700), (700,), 70, "Retro"),
    # Fun & classy
    "bubbly":     ("Bubbly", "Puffy and playful, like 90s kids' TV", "bubbly", (400, 500, 600, 700), (), 84, "Fun & classy"),
    "comic":      ("Comic", "Casual comic-book lettering", "comic", (400, 700), (700,), 86, "Fun & classy"),
    "marker":     ("Marker", "Handwritten, like a whiteboard at the station", "marker", (400,), (), 100, "Fun & classy"),
    "newspaper":  ("Newspaper", "Sturdy serif, like the morning paper", "newspaper", W5, (), 80, "Fun & classy"),
    "fancy":      ("Old Hollywood", "Elegant serif, like a classic movie title", "fancy", W5, I3, 84, "Fun & classy"),
}
SHADOWS = {
    "classic": None,  # the hard 90s drop shadow the pages already have
    "soft": "0 2px 5px rgba(0,0,0,.85),0 0 2px rgba(0,0,0,.9)",
    "thin": "1px 1px 0 rgba(0,0,0,.9),0 0 1px rgba(0,0,0,.6)",
}
SHADOWS_LITE = {"soft": "1px 2px 2px rgba(0,0,0,.9)", "thin": "1px 1px 0 rgba(0,0,0,.9)"}


def font():
    f = env("FONT", "classic").lower()
    return f if f in FONTS else "classic"


def font_faces(key, family="Barlow Condensed", lighter=False):
    """@font-face rules that load font `key` under the name `family`.
    lighter=True points every weight at a file about two steps thinner."""
    _, _, pre, ws, its, adj, _ = FONTS.get(key, FONTS["classic"])
    sa = f"size-adjust:{adj}%;" if adj != 100 else ""
    out = []
    def pick(w, have):
        if lighter:
            w = max(min(have), w - 200)
        return min(have, key=lambda h: abs(h - w))
    for w in (400, 500, 600, 700, 800, 900):
        f = pick(w, ws)
        out.append(f'@font-face{{font-family:"{family}";src:url(/fonts/{pre}-{f}.woff) format("woff");font-weight:{w};font-style:normal;font-display:swap;{sa}}}')
        if its:
            fi = pick(w, its)
            out.append(f'@font-face{{font-family:"{family}";src:url(/fonts/{pre}-{fi}i.woff) format("woff");font-weight:{w};font-style:italic;font-display:swap;{sa}}}')
    return "".join(out)


def font_css(page):
    """The chosen font, weight and text shadow for a page."""
    lighter = env("FONT_WEIGHT", "bold").lower() == "lighter"
    css = [font_faces(font(), lighter=lighter),
           "body{-webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale;font-kerning:normal}"]
    sh = env("TEXT_SHADOW", "classic").lower()
    if SHADOWS.get(sh):
        css.append(f".sh{{text-shadow:{SHADOWS[sh]}!important}}.lite .sh{{text-shadow:{SHADOWS_LITE[sh]}!important}}")
    return "\n".join(css)


def guide_font_css(page):
    """Added last, after the guide style, so it wins. The 2000s guide styles use your font,
    or with Classic, their own 2000s-style font."""
    if page != "tv" or guide_style() == "knas":
        return ""
    if font() != "classic":
        return '#guide,#guide *,#banner,#banner *,#osd{font-family:"Barlow Condensed",Arial,sans-serif!important}'
    # Classic: each 2000s style gets a font stored on your NAS that suits it. (TV boxes don't have
    # the Windows fonts those boxes looked like, and fall back to a wide, blocky default.)
    lighter = env("FONT_WEIGHT", "bold").lower() == "lighter"
    own = GUIDE_FONTS.get(guide_style(), "smooth")
    return font_faces(own, "KNAS Guide", lighter) + '\n#guide,#guide *,#banner,#banner *,#osd{font-family:"KNAS Guide",Arial,sans-serif!important}'


GUIDE_FONTS = {"satellite": "smooth", "cable": "modern", "chrome": "easyread"}


def font_list():
    """For the setup page."""
    return [{"key": k, "name": v[0], "desc": v[1], "group": v[6], "css": font_faces(k, "KNASPV-" + k)} for k, v in FONTS.items()]


# ---------------------------------------------------------------- names & logos
def names():
    station = env("STATION_NAME", "KNAS 42") or "KNAS 42"
    return {
        "station": station,
        "cable": env("CABLE_NAME", "KNAS Cable") or "KNAS Cable",
        "sports": env("SPORTS_NAME", "KNAS Sports") or "KNAS Sports",
        "guide": env("GUIDE_NAME", "TV Guide") or "TV Guide",
        "break1": env("BREAK_LINE1", "Stay Tuned") or "Stay Tuned",
        "break2": env("BREAK_LINE2", "We'll be right back") or "We'll be right back",
        "welcome": env("WELCOME_TEXT", "Welcome to"),
    }


def logo_file(kind):
    if kind not in LOGO_KINDS:
        return None
    for ext in (".png", ".jpg", ".gif", ".webp"):
        p = os.path.join(LOGOS, kind + ext)
        if os.path.isfile(p):
            return p
    return None


def logos():
    out = {}
    for k in LOGO_KINDS:
        p = logo_file(k)
        out[k] = f"/logo/{k}?v={int(os.path.getmtime(p))}" if p else None
    return out


def save_logo(kind, data):
    if kind not in LOGO_KINDS:
        raise ValueError("unknown logo")
    if len(data) > 3 * 1024 * 1024:
        raise ValueError("that picture is too big (3 MB max)")
    ext = next((e for magic, e in LOGO_TYPES.items() if data.startswith(magic)), None)
    if not ext or (ext == ".webp" and data[8:12] != b"WEBP"):
        raise ValueError("please use a PNG, JPG, GIF or WebP picture")
    os.makedirs(LOGOS, exist_ok=True)
    remove_logo(kind)
    p = os.path.join(LOGOS, kind + ext)
    with open(p, "wb") as f:
        f.write(data)
    try:
        os.chmod(p, 0o666)
    except OSError:
        pass


def remove_logo(kind):
    for ext in (".png", ".jpg", ".gif", ".webp"):
        try:
            os.remove(os.path.join(LOGOS, kind + ext))
        except OSError:
            pass


# ---------------------------------------------------------------- sound
def _num(k, d, lo, hi):
    try:
        return max(lo, min(hi, float(env(k, str(d)) or d)))
    except ValueError:
        return d


def audio():
    return {
        "level": env("LEVEL_AUDIO", "on").lower() not in ("off", "no", "0", "false"),
        "strength": env("LEVEL_STRENGTH", "medium").lower(),
        "target": _num("LEVEL_TARGET", 0, -12, 12),        # dB up or down after leveling
        "limit": env("LEVEL_LIMITER", "on").lower() not in ("off", "no", "0", "false"),
        "ceiling": _num("LEVEL_CEILING", -1, -12, 0),       # dB the limiter never goes above
        "fade": _num("LEVEL_FADE_MS", 700, 0, 3000),        # fade-in after changing channel
        "tv": _num("VOL_TV", 100, 0, 200) / 100,
        "music": _num("VOL_MUSIC", 70, 0, 200) / 100,
        "radio": _num("VOL_RADIO", 100, 0, 200) / 100,
        "static": _num("STATIC_VOLUME", 50, 0, 100) / 100,
    }


# ---------------------------------------------------------------- holidays
SEASONS = {   # name: (greeting, accent, ticker, logo band)
    "halloween":    ("Happy Halloween!", "#ff8a1a", "#2a0b3d", "#6a1b9a"),
    "thanksgiving": ("Happy Thanksgiving!", "#ffb347", "#3d1d08", "#b5541c"),
    "christmas":    ("Merry Christmas & Happy Holidays!", "#ffffff", "#6e0d12", "#1f7a3a"),
    "newyear":      ("Happy New Year!", "#ffd700", "#0b0b24", "#c9a400"),
    "valentines":   ("Happy Valentine's Day!", "#ff8fb8", "#4a0a24", "#e0245e"),
    "stpatricks":   ("Happy St. Patrick's Day!", "#7dff8a", "#063d16", "#1a9e3a"),
    "easter":       ("Happy Easter!", "#ffe680", "#3b2b5c", "#9b6bd6"),
    "july4":        ("Happy Fourth of July!", "#ffffff", "#0b1f5c", "#d21f2b"),
    "winter":       ("Stay warm out there!", "#dff4ff", "#0f2a4a", "#4a90c8"),
}


def _easter(y):
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mo = (h + l - 7 * m + 114) // 31
    da = ((h + l - 7 * m + 114) % 31) + 1
    import datetime
    return datetime.date(y, mo, da)


def season_on(day=None):
    """Which holiday it is (or '' if none), for SEASON=auto."""
    import datetime
    from clock import local_today
    d = day or local_today()
    y = d.year
    nov1 = datetime.date(y, 11, 1)
    thanks = nov1 + datetime.timedelta(days=(3 - nov1.weekday()) % 7 + 21)       # 4th Thursday
    eas = _easter(y)
    if d.month == 10:
        return "halloween"
    if datetime.date(y, 11, 1) <= d <= thanks:
        return "thanksgiving"
    if thanks < d <= datetime.date(y, 12, 26):
        return "christmas"
    if d >= datetime.date(y, 12, 27) or d <= datetime.date(y, 1, 2):
        return "newyear"
    if datetime.date(y, 2, 7) <= d <= datetime.date(y, 2, 14):
        return "valentines"
    if datetime.date(y, 3, 10) <= d <= datetime.date(y, 3, 17):
        return "stpatricks"
    if eas - datetime.timedelta(days=7) <= d <= eas:
        return "easter"
    if datetime.date(y, 7, 1) <= d <= datetime.date(y, 7, 5):
        return "july4"
    if env("SEASON_WINTER", "on").lower() != "off" and (d.month in (1, 2) or (d.month == 12)):
        return "winter"
    return ""


def season():
    pick = env("SEASON", "auto").lower()
    name = season_on() if pick == "auto" else (pick if pick in SEASONS else "")
    eff = env("SEASON_EFFECTS", "full").lower()
    if eff not in ("full", "light", "off"):
        eff = "full"
    return {"name": name, "effects": eff, "greeting": SEASONS[name][0] if name and env("SEASON_GREETING", "on").lower() != "off" else "",
            "tune": env("SEASON_TUNE", "on").lower() != "off", "colors": env("SEASON_COLORS", "on").lower() != "off"}


def season_css(page):
    sn = season()
    if not sn["name"] or not sn["colors"]:
        return ""
    _, accent, ticker, band = SEASONS[sn["name"]]
    css = [f":root{{--gold:{accent}}}"]
    if page != "tv":
        css.append(f"footer{{background:linear-gradient(180deg,{light(ticker, .15)},{ticker})!important;box-shadow:inset 0 3px 0 {accent},inset 0 5px 0 {dark(accent, .55)}!important}}")
        css.append(f".crawl b,.title .t2,.clock .dt{{color:{accent}!important}}")
        css.append(f".logo .call,.st-logo b{{background:{band}!important}}")
    else:
        css.append(f".b-num span{{background:{band}!important}}.gr.cur .gcn{{background:linear-gradient(180deg,{band},{dark(band, .35)})!important}}.gr.cur .gcn b,.gr.cur .gcn span{{color:#fff!important;text-shadow:1px 1px 0 rgba(0,0,0,.6)}}")
    return "\n".join(css)


def boot(page):
    """Everything added to a page's <head>."""
    css = font_css(page) + "\n" + theme_css(page)
    if page == "tv" and GUIDE_STYLES.get(guide_style()):
        css = (css + "\n" if css else "") + GUIDE_STYLES[guide_style()]
    gf = guide_font_css(page)
    if gf:
        css += "\n" + gf
    sc = season_css(page)
    if sc:
        css = (css + "\n" if css else "") + sc
    data = {"page": page, "names": names(), "logos": logos(), "audio": audio(), "theme": env("THEME", "classic").lower(),
            "guide": guide_style(), "pip": guide_style() in GUIDE_PIP, "season": season()}
    tag = f'<script>document.documentElement.setAttribute("data-page","{page}")</script>\n' + '<script>window.KNAS=' + json.dumps(data).replace("<", "\\u003c") + ';</script>'
    if css:
        tag += f'\n<style id="knas-theme">\n{css}\n</style>'
    tag += '\n<script src="/knas-common.js"></script>'
    if data["season"]["name"]:
        tag += '\n<script src="/knas-season.js" defer></script>'
    return tag
