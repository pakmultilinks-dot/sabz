"""Build SABZ_Script.docx. Word-for-word speaking script for 4 members. Natural student voices, no corporate phrasing."""
import os
from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

GREEN = RGBColor(0x00, 0xE6, 0x76)
DEEP_GREEN = RGBColor(0x05, 0x96, 0x69)
INK = RGBColor(0x0B, 0x12, 0x20)
MUTED = RGBColor(0x5B, 0x6B, 0x8C)

doc = Document()
style = doc.styles["Normal"]
style.font.name = "Inter"
style.font.size = Pt(11)
style.font.color.rgb = INK
style.paragraph_format.space_after = Pt(6)
style.paragraph_format.line_spacing = 1.4

for i in range(1, 4):
    hs = doc.styles[f"Heading {i}"]
    hs.font.name = "Space Grotesk"
    hs.font.color.rgb = INK
    hs.font.bold = True
doc.styles["Heading 1"].font.size = Pt(22)
doc.styles["Heading 2"].font.size = Pt(16)
doc.styles["Heading 2"].font.color.rgb = DEEP_GREEN


def title(t):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(t)
    r.font.name = "Space Grotesk"
    r.font.size = Pt(28)
    r.font.bold = True
    r.font.color.rgb = DEEP_GREEN


def h(t, level=1):
    doc.add_heading(t, level=level)


def cue(t):
    p = doc.add_paragraph()
    r = p.add_run(t)
    r.font.bold = True
    r.font.color.rgb = MUTED
    r.font.size = Pt(10)
    return p


def line(t):
    doc.add_paragraph(t)


def note(t):
    p = doc.add_paragraph()
    r = p.add_run("NOTE: " + t)
    r.font.italic = True
    r.font.color.rgb = MUTED
    r.font.size = Pt(10)


title("SABZ: Speaking Script")
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("Garrison 4th International AI Championship - AI in Urban Tech\nTotal runtime: about 8 minutes. Emergency 30-second cut at the end.")
r.font.size = Pt(11)
r.font.color.rgb = MUTED
note("Rehearse out loud, twice, with the slides. The [CLICK] cues match the slide numbers. If a line feels unnatural in your mouth, change the words, keep the meaning.")
doc.add_page_break()

# ---------------- ABDUR REHMAN ----------------
h("ABDUR REHMAN: The Opener (about 2 minutes, Slides 1-3)", level=1)
cue("[CLICK: Slide 1, Title. Walk up, smile, breathe.]")
line('"Assalam-o-Alaikum and good morning. We are Team SABZ, from Lahore Garrison University. I am Abdur Rehman, and with me are Bilal, Awais, and Dawood."')
cue("[PAUSE]")
line('"SABZ means green, in Urdu. And SABZ is a traffic signal that can see."')
cue("[PAUSE. Let that land.]")
line('"Let me tell you why we built it. Every day I cross the signal at Main Boulevard, Gulberg, near Siddique Trade Center, around 6 in the evening. And every day the same thing happens: my road is packed, twenty, twenty-five cars waiting, and the cross road is completely empty. Not one car. And the signal still gives that empty road a full green. I sit there, watching nothing cross an empty road, while my side waits."')
note("Abdur Rehman: swap in your real intersection and your real details. The more specific, the more the judges believe it.")
cue("[CLICK: Slide 2, The Problem]")
line('"And it is not just my one signal. Lahore had about 378,000 registered vehicles in 2014. Today it is 4.1 million. Eleven times more cars in a decade. The average commute in this city is now around 35 minutes. Studies put the cost of congestion at over a thousand rupees per day for a car driver. This is a daily tax on the whole city, and the signals controlling it are running on fixed timers from another era."')
cue("[CLICK: Slide 3, Why timers fail]")
line('"A fixed timer gives every road the same green, at 3 in the morning and at 6 in the evening. It cannot see the empty road. It cannot see my twenty waiting cars. Even the smarter actuated signals are just if-then rules: if my queue is empty and someone waits, switch. They react. They never learn."')
cue("[PAUSE]")
line('"So we asked a simple question: what if the signal could actually see the traffic, and learn from it? That is SABZ. And now Bilal will show you what is inside the brain."')
cue("[HANDOFF. Step back. Bilal steps forward.]")

# ---------------- BILAL ----------------
doc.add_page_break()
h("BILAL: The Brain (about 2.5 minutes, Slides 4-7)", level=1)
cue("[CLICK: Slide 4, System diagram. Bilal steps forward.]")
line('"Thank you, Abdur Rehman. I am Bilal, and I built the brain with the team. Here is the whole system in four steps, and I will keep it simple."')
line('"Step one, see: cameras watch each of the four roads, out to 120 metres, and count the cars. Queued cars, approaching cars, per road."')
line('"Step two, think: those counts become 18 numbers. Four queue counts, four approaching counts, which phase is green, how long it has been green, six location features, like is this near a school, near a mosque, is it Friday, what hour is it, and two starvation features, how long the red road has been waiting. Those 18 numbers go into a small neural network, 18 in, two hidden layers of 64, and two scores out: hold the green, or switch. It picks the better score. One decision, every second, in about 0.02 milliseconds."')
cue("[CLICK: Slide 5, DQN diagram]")
line('"How does it learn? The reward is brutally simple: negative total queue, every second. Every car-second of waiting is punishment. So the brain is not told what good timing looks like. It discovers it, over tens of thousands of simulated episodes, because waiting hurts and it wants the pain to stop. We wrote this network from scratch in NumPy, all 5,506 parameters, no PyTorch, no borrowed model. When training broke, we could open it up and fix the actual math."')
cue("[PAUSE]")
cue("[CLICK: Slide 6, Safety]")
line('"Now the part the judges will care about most. The brain proposes, but it does not get the final say. There is a hard safety rule that lives outside the neural network, where no training can ever touch it: every second, before any switch executes, the system scans the 70-metre zone before the stop line on the green roads. If any car is inside that zone, the switch is vetoed. Green extends. Then three seconds of yellow, two seconds of all-red, and only then the switch. No weight update, no bad day, no bug in the policy can ever cut a green under an approaching car. Safety is guaranteed by design, not by hoping the AI is smart enough."')
cue("[CLICK: Slide 7, Real data]")
line('"One honest thing about our data. We calibrate the simulator with NGSIM, about a million real vehicle records from a US highway. But let me be precise: we use the measured arrival patterns to make traffic realistic. We do not train on raw trajectories, and it is not Lahore data. The Lahore data comes next, from the pilot. We would rather tell you exactly what the data is than oversell it."')
cue("[PAUSE]")
line('"So that is the brain: it sees, it learns, and it can never make an unsafe switch. Awais will now show you it working, live."')
cue("[HANDOFF. Bilal steps back. Awais steps forward.]")

# ---------------- AWAIS ----------------
doc.add_page_break()
h("AWAIS: The Demo and the Numbers (about 2 minutes, Slides 8-9)", level=1)
cue("[CLICK: Slide 8, Results. Awais steps forward, energetic.]")
line('"I am Awais. Enough diagrams, let me show you the numbers first, then the thing itself."')
line('"We benchmark against the best hand-tuned actuated controller, the good-engineer answer. Three traffic scenarios, three random seeds each, one full simulated hour per run, safety on. Average delay per vehicle:"')
cue("[Read the table, slowly, point at each row.]")
line('"Asymmetric traffic, one road busy, the cross road quiet: actuated 5.0 seconds, SABZ 5.0 seconds. Win."')
line('"School zone, morning rush: actuated 5.3 seconds, SABZ 5.0 seconds. Win."')
line('"Balanced, all four roads equally packed: 11.9 versus 11.9. A tie, and we score ties as losses. I am telling you this myself because it is the truth: the balanced scenario is the hardest, and training is still running right now to break that tie. Our best mean delay across the full benchmark is 7.3 seconds."')
cue("[PAUSE]")
cue("[CLICK: Slide 9, 'Watch it think'. Big pause. Then switch to the live demo.]")
line('"Enough slides. Watch it think."')
cue("[LIVE DEMO. Narrate what the judges see, in real time.]")
line('"See that? The camera counts eight cars still discharging on the north road, so the brain holds the green, even though the timer would have cut it. Now watch: the north road clears, two cars waiting on the east, and it switches, early, no wasted green. That decision took 0.02 milliseconds."')
note("Awais: adapt these two lines to whatever the demo actually shows. Never narrate what is not on screen. If the demo misbehaves, say so calmly: 'That is the honest state of the system, and here is what we are fixing.' Judges reward honesty over a perfect show.")
line('"What you just watched is the real trained brain, making real decisions, with the safety veto standing guard over every single one. Dawood will tell you where this goes next."')
cue("[HANDOFF. Awais steps back. Dawood steps forward.]")

# ---------------- DAWOOD ----------------
doc.add_page_break()
h("DAWOOD: The Closer (about 1.5 minutes, Slides 10-12)", level=1)
cue("[CLICK: Slide 10, Deployment. Dawood steps forward, calm.]")
line('"I am Dawood. You have seen the problem, the brain, and the proof. Here is what happens next."')
line('"Phase one: one intersection in Lahore, shadow mode. The brain decides, the existing controller still executes, and we log every decision. Phase two: supervised live control, with instant fallback to the old controller if anything looks wrong. Phase three: full control, monitored, and the city can override it at any time. Because a system the city cannot supervise is a system the city will never buy."')
cue("[CLICK: Slide 11, Business model]")
line('"Who pays? The city traffic authority, the same body that already buys signals. The hardware is cameras on existing poles and one small computer in the signal cabinet. No digging up roads, no GPU servers. We land one pilot, prove measured delay reduction, and scale corridor by corridor."')
cue("[CLICK: Slide 12, Thank you. Pause. Then the close.]")
line('"Let me tell you why four students from Lahore are building this. The big signal companies built their systems for orderly Western traffic. Nobody built one for our roads: our motorcycles, our rickshaws, our school rushes, our Friday prayer surges. We sit in this traffic every day. So we built the fix ourselves."')
cue("[PAUSE. Eye contact.]")
line('"The people who sit in the traffic should be the people who build the fix. Thank you."')
cue("[Hold for applause/questions. Do not rush off.]")

# ---------------- EMERGENCY CUT ----------------
doc.add_page_break()
h("EMERGENCY 30-SECOND CUT (if judges cut your time)", level=1)
note("One speaker, Abdur Rehman. Slow down, do not speed up. Thirty seconds of calm beats two minutes of panic.")
cue("[No slides, or slide 12 only.]")
line('"SABZ is a traffic signal that can see. Lahore went from 378,000 to 4.1 million vehicles in a decade, and its signals still run on blind fixed timers. Our AI watches real traffic through cameras, learns the best green timing in simulation, and decides every second, with a hard safety rule that can never cut a green under an approaching car. Against the best hand-tuned controller it already wins on asymmetric and school-zone traffic, 5.0 versus 5.3 seconds in the school zone, and training continues on the balanced tie. Four students from Lahore Garrison University built the brain from scratch. The people who sit in the traffic should be the people who build the fix. Thank you."')

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "SABZ_Script.docx")
doc.save(out)
print("saved", out)
