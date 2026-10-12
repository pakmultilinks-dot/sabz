"""SABZ LLM layer: the system explains itself and reasons about traffic.

Two jobs:
1. explain_decision(): why did the signal do what it just did, in plain
   English or Urdu. For judges, for traffic officers, for the public.
2. daily_report(): end-of-day summary of what the junction saw and how
   the controller handled it, with suggested plan tweaks.

LLM backend: OpenRouter (https://openrouter.ai), key from the
OPENROUTER_API_KEY environment variable, model from SABZ_LLM_MODEL
(default: the free Haiku-class model). The key is NEVER hardcoded,
never logged, never committed.

When no key/network is available, explain_decision() falls back to
honest template explanations clearly marked as templates, so the
product keeps working offline and nobody is misled about what
generated the words.
"""
import os
import json
import urllib.request

OPENROUTER_URL = "https://api.openrouter.ai/api/v1/chat/completions"
MODEL = os.environ.get("SABZ_LLM_MODEL", "claude-haiku-5.5:free")


def _llm_available():
    return bool(os.environ.get("OPENROUTER_API_KEY"))


def _llm_chat(system, user, max_tokens=300):
    """Call the LLM. Raises RuntimeError on any failure."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY not set")
    body = json.dumps({
        "model": MODEL,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }).encode()
    req = urllib.request.Request(
        OPENROUTER_URL, data=body,
        headers={"Authorization": "Bearer " + key,
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        out = json.load(r)
    return out["choices"][0]["message"]["content"].strip()


def describe_state(st):
    """One-paragraph machine description of the intersection state."""
    q = st["queues"]
    a = st["approaching"]
    return (
        "Phase %s, green elapsed %ds. Queued vehicles: N=%d S=%d E=%d W=%d. "
        "Approaching within 120m: N=%d S=%d E=%d W=%d. "
        "Safety holds so far today: %d. Decision just taken: %s." % (
            st["phase"], st["green_elapsed"],
            q["N"], q["S"], q["E"], q["W"],
            a["N"], a["S"], a["E"], a["W"],
            st.get("safety_holds", 0), st["decision"]))


def _template_explain(st, lang):
    q = st["queues"]
    busy = max(q, key=q.get)
    if lang == "ur":
        return ("[template] Signal ne %s road ko sabz batti di kyunke wahan "
                "sab se zyada %d gaariyan intezar kar rahi thin. "
                "Khaali road ko green de kar waqt zaya nahi kiya gaya." % (
                    busy, q[busy]))
    return ("[template] Green went to the %s approach because it had the "
            "longest queue (%d waiting). No green time was wasted on the "
            "empty approaches." % (busy, q[busy]))


def explain_decision(st, lang="en"):
    """Explain one signal decision. lang: 'en' or 'ur'.

    Returns (text, source) where source is 'llm' or 'template'.
    """
    if not _llm_available():
        return _template_explain(st, lang), "template"
    sys = ("You are SABZ, an AI traffic signal controller in Lahore, Pakistan. "
           "Explain your signal decisions in 2 short sentences, no jargon.")
    if lang == "ur":
        sys += " Answer in simple Urdu (Roman Urdu is fine)."
    try:
        text = _llm_chat(sys, describe_state(st))
        return text, "llm"
    except Exception:
        return _template_explain(st, lang), "template"


def daily_report(day, lang="en"):
    """day: dict with totals (vehicles, avg_delay, safety_holds, per_hour...).
    Returns (text, source)."""
    summary = ("Vehicles served: %d. Average delay per vehicle: %.1fs. "
               "Safety holds (green extended for approaching cars): %d. "
               "Busiest hour: %s." % (
                   day["vehicles"], day["avg_delay"],
                   day["safety_holds"], day.get("busiest_hour", "-")))
    if not _llm_available():
        if lang == "ur":
            return "[template] " + summary, "template"
        return "[template] " + summary, "template"
    sys = ("You are SABZ, an AI traffic signal controller. Write a 4-sentence "
           "end-of-day traffic report for city officials from the data given. "
           "End with one concrete suggestion.")
    if lang == "ur":
        sys += " Answer in simple Urdu."
    try:
        return _llm_chat(sys, summary, max_tokens=400), "llm"
    except Exception:
        return "[template] " + summary, "template"


if __name__ == "__main__":
    demo = {"phase": "NS", "green_elapsed": 23,
            "queues": {"N": 14, "S": 11, "E": 1, "W": 0},
            "approaching": {"N": 3, "S": 2, "E": 0, "W": 0},
            "safety_holds": 41, "decision": "hold green (queue still long)"}
    for lang in ("en", "ur"):
        text, src = explain_decision(demo, lang)
        print("[%s/%s] %s" % (lang, src, text))
