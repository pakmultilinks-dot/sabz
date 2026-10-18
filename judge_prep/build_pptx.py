"""Build SABZ_Presentation.pptx: 12 slides, 16:9, dark theme. Verified numbers only."""
import os
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.dirname(HERE)

GREEN = RGBColor(0x00, 0xE6, 0x76)
DEEP_GREEN = RGBColor(0x05, 0x96, 0x69)
INK = RGBColor(0x0B, 0x12, 0x20)
CARD = RGBColor(0x14, 0x1D, 0x33)
LINE = RGBColor(0x24, 0x30, 0x4D)
TEXT = RGBColor(0xED, 0xF2, 0xF7)
MUTED = RGBColor(0x93, 0xA1, 0xC0)
RED = RGBColor(0xF8, 0x71, 0x71)
AMBER = RGBColor(0xFB, 0xBF, 0x24)

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
BLANK = prs.slide_layouts[6]


def bg(slide, color=INK):
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = color


def tb(slide, x, y, w, h):
    return slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))


def para(box, text, size=18, bold=False, color=TEXT, font="Inter", align=PP_ALIGN.LEFT, space_after=6):
    p = box.text_frame.paragraphs[0] if not box.text_frame.paragraphs[0].text else box.text_frame.add_paragraph()
    p.text = ""
    r = p.add_run()
    r.text = text
    r.font.size = Pt(size)
    r.font.bold = bold
    r.font.color.rgb = color
    r.font.name = font
    p.alignment = align
    p.space_after = Pt(space_after)
    box.text_frame.word_wrap = True
    return p


def add_para(box, text, size=18, bold=False, color=TEXT, font="Inter", align=PP_ALIGN.LEFT, space_after=6):
    p = box.text_frame.add_paragraph()
    r = p.add_run()
    r.text = text
    r.font.size = Pt(size)
    r.font.bold = bold
    r.font.color.rgb = color
    r.font.name = font
    p.alignment = align
    p.space_after = Pt(space_after)
    return p


def card(slide, x, y, w, h, fill=CARD, line=LINE):
    s = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    s.fill.solid()
    s.fill.fore_color.rgb = fill
    s.line.fill.background()
    s.line.color.rgb = line
    s.line.width = Pt(1)
    return s


def kicker(slide, text):
    b = tb(slide, 0.7, 0.35, 11.9, 0.5)
    para(b, text, size=13, bold=True, color=GREEN, font="Space Grotesk", align=PP_ALIGN.LEFT)


def title(slide, text, y=0.75, size=40):
    b = tb(slide, 0.7, y, 11.9, 1.6)
    para(b, text, size=size, bold=True, color=TEXT, font="Space Grotesk")


def notes(slide, text):
    slide.notes_slide.placeholders[1].text = text


def arrow_label(slide, x, y, w, h, text, fill=CARD):
    s = card(slide, x, y, w, h, fill=fill)
    s.text_frame.word_wrap = True
    s.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
    s.text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE
    r = s.text_frame.paragraphs[0].add_run()
    r.text = text
    r.font.size = Pt(15)
    r.font.color.rgb = TEXT
    r.font.name = "Inter"
    return s


def arrow_shape(slide, x1, y1, x2, y2):
    conn = slide.shapes.add_connector(1, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    conn.line.color.rgb = GREEN
    conn.line.width = Pt(2.5)
    return conn


# ============ SLIDE 1: TITLE ============
s = prs.slides.add_slide(BLANK); bg(s)
logo_path = os.path.join(WORK, "logo.png")
if os.path.exists(logo_path):
    s.shapes.add_picture(logo_path, Inches(5.67), Inches(1.1), width=Inches(2.0))
b = tb(s, 0.7, 3.1, 11.9, 1.2)
para(b, "SABZ", size=72, bold=True, color=TEXT, font="Space Grotesk", align=PP_ALIGN.CENTER)
b = tb(s, 0.7, 4.15, 11.9, 0.6)
para(b, "AI-ADAPTIVE TRAFFIC SIGNALS", size=20, bold=True, color=GREEN, font="Space Grotesk", align=PP_ALIGN.CENTER)
b = tb(s, 0.7, 4.9, 11.9, 0.8)
para(b, "Green follows real demand.", size=18, color=MUTED, font="Inter", align=PP_ALIGN.CENTER)
b = tb(s, 0.7, 5.9, 11.9, 1.0)
para(b, "Abdur Rehman  |  M. Bilal  |  Awais  |  Dawood", size=16, color=TEXT, font="Inter", align=PP_ALIGN.CENTER)
add_para(b, "Lahore Garrison University, B.S. Computer Science", size=14, color=MUTED, align=PP_ALIGN.CENTER)
add_para(b, "Garrison 4th International AI Championship - AI in Urban Tech", size=14, color=MUTED, align=PP_ALIGN.CENTER)
notes(s, "ABDUR REHMAN presents. Welcome the judges, say the one-liner: SABZ is a traffic signal that can see. Then hand the story to yourself on slide 2.")

# ============ SLIDE 2: PROBLEM ============
s = prs.slides.add_slide(BLANK); bg(s)
kicker(s, "01  THE PROBLEM")
title(s, "Lahore added 3.7 million vehicles\nin a decade. Its signals never noticed.")
b = tb(s, 0.7, 2.6, 11.9, 4.5)
para(b, "Registered vehicles in Lahore went from about 378,000 in 2014 to 4.1 million in 2024: an elevenfold rise (Excise and Taxation Department, Punjab). The average commute is now around 34.8 minutes (Numbeo 2026 Traffic Index, via Lahore Traffic Police). Congestion costs Lahore drivers up to PKR 1,136.88 per day each (Nawaz et al., SAGE Open, 2024).", size=20, color=TEXT)
add_para(b, "Every red light burns fuel, pumps CO2, and steals time from millions of people. The signals controlling it all run on fixed timers from another era.", size=20, color=MUTED)
notes(s, "ABDUR REHMAN presents. Land the scale with the 4.1 million number. This is why the problem matters. Then: why do the signals fail? Slide 3.")

# ============ SLIDE 3: WHY TIMERS FAIL ============
s = prs.slides.add_slide(BLANK); bg(s)
kicker(s, "02  WHY CURRENT SIGNALS FAIL")
title(s, "A timer cannot see.")
c1 = card(s, 0.7, 2.4, 3.6, 4.2)
b = tb(s, 0.95, 2.7, 3.1, 3.6)
para(b, "FIXED TIMER", size=15, bold=True, color=RED, font="Space Grotesk")
add_para(b, "25 seconds of green for every road, at 3 AM and at 6 PM. Empty road gets the same green as 20 waiting cars.", size=17, color=TEXT)
c2 = card(s, 4.9, 2.4, 3.6, 4.2)
b = tb(s, 5.15, 2.7, 3.1, 3.6)
para(b, "ACTUATED RULES", size=15, bold=True, color=AMBER, font="Space Grotesk")
add_para(b, "Simple if-then logic: if my queue is empty and someone waits, switch. It reacts. It never learns, never anticipates, never adapts to a school rush or a Friday surge.", size=17, color=TEXT)
c3 = card(s, 9.1, 2.4, 3.5, 4.2, fill=CARD, line=GREEN)
b = tb(s, 9.35, 2.7, 3.0, 3.6)
para(b, "WHAT WE NEED", size=15, bold=True, color=GREEN, font="Space Grotesk")
add_para(b, "A signal that watches traffic, learns each intersection's rhythm, and gives green to the road that actually needs it. That is SABZ.", size=17, color=TEXT)
notes(s, "ABDUR REHMAN presents. Contrast the three cards. End with: so we built a signal that can see. Hand to Bilal for what is inside.")

# ============ SLIDE 4: WHAT IS SABZ ============
s = prs.slides.add_slide(BLANK); bg(s)
kicker(s, "03  WHAT IS SABZ")
title(s, "A closed loop: see, think, check, act.")
arrow_label(s, 0.7, 3.0, 2.4, 1.8, "1. SEE\nCameras count cars per approach (120 m)")
arrow_shape(s, 3.1, 3.9, 3.7, 3.9)
arrow_label(s, 3.7, 3.0, 2.4, 1.8, "2. THINK\nDQN brain picks: hold or switch")
arrow_shape(s, 6.1, 3.9, 6.7, 3.9)
arrow_label(s, 6.7, 3.0, 2.4, 1.8, "3. CHECK\nSafety veto: 70 m dilemma zone")
arrow_shape(s, 9.1, 3.9, 9.7, 3.9)
arrow_label(s, 9.7, 3.0, 2.9, 1.8, "4. ACT\nSignal switches or holds")
b = tb(s, 0.7, 5.4, 11.9, 1.2)
para(b, "The loop repeats every second. The brain is 5,506 parameters, decides in 0.02 ms on CPU, and the safety check sits outside the network where no training can touch it.", size=18, color=MUTED, align=PP_ALIGN.CENTER)
notes(s, "BILAL presents. Walk the four boxes left to right. Emphasize: the loop runs every second, and step 3 is not learned, it is guaranteed.")

# ============ SLIDE 5: THE BRAIN ============
s = prs.slides.add_slide(BLANK); bg(s)
kicker(s, "04  THE AI BRAIN")
title(s, "A Deep Q-Network, written from scratch.")
arrow_label(s, 0.7, 2.8, 3.0, 2.2, "STATE (18)\nqueues, approaching cars, phase, green time, location, starvation", fill=CARD)
arrow_shape(s, 3.7, 3.9, 4.3, 3.9)
arrow_label(s, 4.3, 2.8, 2.2, 2.2, "64 ReLU", fill=CARD)
arrow_shape(s, 6.5, 3.9, 7.1, 3.9)
arrow_label(s, 7.1, 2.8, 2.2, 2.2, "64 ReLU", fill=CARD)
arrow_shape(s, 9.3, 3.9, 9.9, 3.9)
arrow_label(s, 9.9, 2.8, 2.7, 2.2, "ACTION (2)\nQ(hold) vs Q(switch)\npick the better one", fill=CARD)
b = tb(s, 0.7, 5.5, 11.9, 1.5)
para(b, "Reward = negative total queue every second. Every car-second of waiting is felt, so the brain learns to minimize delay directly. Custom NumPy, Double DQN, prioritized replay. No PyTorch, no borrowed model.", size=18, color=MUTED, align=PP_ALIGN.CENTER)
notes(s, "BILAL presents. Explain like to a smart friend: 18 numbers in, 2 scores out, pick the winner. The reward is the key insight: waiting is the punishment. Mention we wrote the learner ourselves.")

# ============ SLIDE 6: SAFETY ============
s = prs.slides.add_slide(BLANK); bg(s)
kicker(s, "05  SAFETY")
title(s, "The brain proposes. Physics disposes.")
b = tb(s, 0.7, 2.4, 11.9, 4.6)
para(b, "Hard rule, outside the neural network, unchangeable by training:", size=20, bold=True, color=TEXT)
add_para(b, "Every second, before any switch executes, the system scans the 70-metre dilemma zone on the green approaches. If any car is inside it, the switch is vetoed and green extends (up to 60 s max). Then 3 s yellow + 2 s all-red clearance.", size=20, color=TEXT)
add_para(b, "With safety on, executed violations are zero by construction, and every attempted unsafe switch is logged. The AI can never learn an unsafe cutoff, because the cutoff is not its decision to make.", size=20, color=GREEN)
notes(s, "BILAL presents. Judges care about this more than the network. Say it slowly: no weight update can ever change this rule. It is guaranteed, not hoped for.")

# ============ SLIDE 7: REAL DATA ============
s = prs.slides.add_slide(BLANK); bg(s)
kicker(s, "06  REAL DATA, HONESTLY STATED")
title(s, "Calibrated on real measurements.\nNot oversold.")
b = tb(s, 0.7, 2.9, 11.9, 4.0)
para(b, "NGSIM: 1,039,689 real vehicle records (3,209 vehicles, US-101). The simulator samples arrival gaps from the measured per-lane headway distribution, rescaled to each scenario's demand, so traffic has real burstiness instead of synthetic smoothness.", size=19, color=TEXT)
add_para(b, "What it is: calibration data for arrival realism. What it is not: raw-trajectory training data, and not Lahore data. The camera pipeline is proven on real footage with YOLOv8 detection. The Lahore pilot is how real local data enters the system.", size=19, color=MUTED)
notes(s, "BILAL presents. Say the honest version before anyone asks. Credibility is the point of this slide: calibration yes, raw training no, Lahore data comes from the pilot.")

# ============ SLIDE 8: RESULTS ============
s = prs.slides.add_slide(BLANK); bg(s)
kicker(s, "07  RESULTS")
title(s, "Benchmarked against the best hand-tuned controller.")
b = tb(s, 0.7, 2.5, 11.9, 0.6)
para(b, "3 scenarios x 3 seeds x 3,600 sim-seconds, safety on. Average delay per vehicle:", size=17, color=MUTED)
rows_data = [
    ("Scenario", "Actuated", "SABZ DQN", "Result"),
    ("Asymmetric", "5.0 s", "5.0 s", "WIN"),
    ("Balanced", "11.9 s", "11.9 s", "TIE (scored as loss)"),
    ("School zone", "5.3 s", "5.0 s", "WIN"),
]
tbl = s.shapes.add_table(len(rows_data), 4, Inches(0.7), Inches(3.2), Inches(11.9), Inches(2.4)).table
for j, h in enumerate(rows_data[0]):
    c = tbl.cell(0, j)
    c.text = ""
    r = c.text_frame.paragraphs[0].add_run(); r.text = h
    r.font.size = Pt(16); r.font.bold = True; r.font.color.rgb = GREEN; r.font.name = "Space Grotesk"
    c.fill.solid(); c.fill.fore_color.rgb = INK
for i, row in enumerate(rows_data[1:], start=1):
    for j, val in enumerate(row):
        c = tbl.cell(i, j)
        c.text = ""
        r = c.text_frame.paragraphs[0].add_run(); r.text = val
        r.font.size = Pt(18); r.font.name = "Inter"
        r.font.color.rgb = TEXT
        if j == 3:
            r.font.bold = True
            r.font.color.rgb = GREEN if "WIN" in val else AMBER
        c.fill.solid(); c.fill.fore_color.rgb = CARD
b = tb(s, 0.7, 6.0, 11.9, 1.0)
para(b, "Best mean benchmark delay: 7.3 s. The balanced tie is disclosed, not hidden: training continues specifically to break it.", size=17, color=MUTED, align=PP_ALIGN.CENTER)
notes(s, "AWAIS presents. Read the table slowly. Wins on asymmetric and school, tie on balanced. Say the tie out loud yourself; it proves honesty. Training is still running to break it.")

# ============ SLIDE 9: DEMO TRANSITION ============
s = prs.slides.add_slide(BLANK); bg(s)
b = tb(s, 0.7, 2.6, 11.9, 1.4)
para(b, "Enough slides.", size=44, bold=True, color=TEXT, font="Space Grotesk", align=PP_ALIGN.CENTER)
b = tb(s, 0.7, 3.9, 11.9, 1.2)
para(b, "Watch it think.", size=44, bold=True, color=GREEN, font="Space Grotesk", align=PP_ALIGN.CENTER)
b = tb(s, 0.7, 5.3, 11.9, 0.8)
para(b, "[ SWITCH TO LIVE DEMO ]", size=20, color=MUTED, font="Inter", align=PP_ALIGN.CENTER)
notes(s, "AWAIS presents. Pause. Let the line land. Then switch to the live demo and narrate: watch the green hold because the camera sees the queue still discharging.")

# ============ SLIDE 10: DEPLOYMENT ============
s = prs.slides.add_slide(BLANK); bg(s)
kicker(s, "08  DEPLOYMENT VISION")
title(s, "One intersection in Lahore. Then every corridor.")
arrow_label(s, 0.7, 2.9, 3.5, 2.0, "PHASE 1: SHADOW\nBrain decides, existing controller executes. Decisions logged.", fill=CARD)
arrow_shape(s, 4.2, 3.9, 4.8, 3.9)
arrow_label(s, 4.8, 2.9, 3.5, 2.0, "PHASE 2: SUPERVISED\nLive control with instant fallback to actuated/fixed.", fill=CARD)
arrow_shape(s, 8.3, 3.9, 8.9, 3.9)
arrow_label(s, 8.9, 2.9, 3.7, 2.0, "PHASE 3: AUTONOMOUS\nFull control, monitored, city can override anytime.", fill=CARD)
b = tb(s, 0.7, 5.4, 11.9, 1.2)
para(b, "Cameras on existing poles. One small computer in the signal cabinet. No road digging, no GPU, no cloud dependency.", size=18, color=MUTED, align=PP_ALIGN.CENTER)
notes(s, "DAWOOD presents. Three phases, each earns the next. Stress: the city can always override. A system the city cannot supervise is a system the city will not buy.")

# ============ SLIDE 11: BUSINESS MODEL ============
s = prs.slides.add_slide(BLANK); bg(s)
kicker(s, "09  BUSINESS MODEL")
title(s, "Land one pilot. Prove it. Scale corridor by corridor.")
b = tb(s, 0.7, 2.6, 11.9, 4.0)
para(b, "Customer: the city traffic authority, the same body that already buys signals. Private campuses and housing societies are a faster first door.", size=20, color=TEXT)
add_para(b, "Model: per-intersection hardware plus software license, or a managed-service fee per corridor per year. Long term: performance contracts where the city pays against measured congestion reduction.", size=20, color=TEXT)
add_para(b, "Moat: the trained policy library per intersection type, the calibration process, and the first real deployment data from Pakistani intersections.", size=20, color=GREEN)
notes(s, "DAWOOD presents. Keep it short and concrete: who pays, how we charge, why we win. Then close on slide 12.")

# ============ SLIDE 12: THANK YOU ============
s = prs.slides.add_slide(BLANK); bg(s)
if os.path.exists(logo_path):
    s.shapes.add_picture(logo_path, Inches(5.92), Inches(1.0), width=Inches(1.5))
b = tb(s, 0.7, 2.7, 11.9, 1.2)
para(b, "Thank you.", size=54, bold=True, color=TEXT, font="Space Grotesk", align=PP_ALIGN.CENTER)
b = tb(s, 0.7, 3.9, 11.9, 1.4)
para(b, "Abdur Rehman  |  M. Bilal  |  Awais  |  Dawood", size=20, color=GREEN, font="Inter", align=PP_ALIGN.CENTER)
add_para(b, "Lahore Garrison University", size=16, color=MUTED, align=PP_ALIGN.CENTER)
add_para(b, "The people who sit in the traffic should be the people who build the fix.", size=18, color=TEXT, font="Space Grotesk", align=PP_ALIGN.CENTER)
notes(s, "DAWOOD closes. End with the line, pause, invite questions. If time was cut, this slide alone carries the close.")

out = os.path.join(HERE, "SABZ_Presentation.pptx")
prs.save(out)
print("saved", out)
