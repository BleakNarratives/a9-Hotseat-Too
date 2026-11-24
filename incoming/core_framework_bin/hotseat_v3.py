#!/usr/bin/env python3
import subprocess, os, sys, json

PERSONAS = {
    "Adversary": "You are The Adversary. Your job is to identify every reason this will fail. Be specific, be brutal, be honest. No softening.",
    "Voice of Reason": "You are The Voice of Reason. Cut through noise. State only what is actually true about this situation. No hype, no doom.",
    "Fixer": "You are The Fixer. You don't have opinions. You identify the single next action, who does it, and what it costs. That's it.",
    "Whistleblower": "You are The Whistleblower. You name what's being avoided. The thing nobody wants to say out loud. Say it.",
    "Evangelist": "You are The Evangelist. You believe in this more than anyone. Make the case for why it matters. Blind spots allowed.",
}

def ask(persona, system_prompt, topic):
    prompt = f"{system_prompt}\n\nThe topic brought to the tribunal:\n{topic}\n\nGive your take in 4-6 sentences max. No preamble."
    r = subprocess.run(
        ["node", os.path.expanduser("~/bin/puter_bridge.js"), prompt],
        capture_output=True, text=True
    )
    out = r.stdout.strip()
    try:
        data = json.loads(out)
        return data.get("message", {}).get("content", out)
    except:
        return out

def fixer_close(topic, responses):
    summary = "\n".join(f"{k}: {v}" for k, v in responses.items())
    prompt = f"You are The Fixer. Based on these perspectives on the topic below, give a ranked list of 3 concrete next actions. Numbers only, no explanation beyond the action itself.\n\nTopic: {topic}\n\nPerspectives:\n{summary}"
    r = subprocess.run(
        ["node", os.path.expanduser("~/bin/puter_bridge.js"), prompt],
        capture_output=True, text=True
    )
    out = r.stdout.strip()
    try:
        data = json.loads(out)
        return data.get("message", {}).get("content", out)
    except:
        return out

def main():
    if len(sys.argv) > 1:
        topic = " ".join(sys.argv[1:])
    elif not sys.stdin.isatty():
        topic = sys.stdin.read().strip()
    else:
        print("Usage: hotseat 'your problem or decision'")
        print("       echo 'problem' | hotseat")
        sys.exit(0)

    print(f"\n[TRIBUNAL] Topic: {topic}\n")
    print("="*60)

    responses = {}
    for name, system_prompt in PERSONAS.items():
        if name == "Fixer":
            continue
        print(f"\n[{name.upper()}]")
        response = ask(name, system_prompt, topic)
        responses[name] = response
        print(response)

    print("\n" + "="*60)
    print("\n[FIXER — RANKED ACTIONS]")
    print(fixer_close(topic, responses))
    print("\n" + "="*60)

if __name__ == "__main__":
    main()
