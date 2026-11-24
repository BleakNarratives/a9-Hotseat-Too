"""
[DNA_TAG]
ORIGIN: Moto4_A9
PILLAR: valet_concierge
PATH: app.py
LAST_SYNC: 2026-08-02T01:12:58Z
[/DNA_TAG]
"""
import gradio as gr
import requests
import json
import time
import os
from datetime import datetime

from vault_loader import get_secret
OPENROUTER_KEY = get_secret("OPENROUTER_KEY") or get_secret("OPENROUTER_API_KEY")
MODELS = {
    "Skeptic1": "deepseek/deepseek-r1:free",
    "Skeptic2": "qwen/qwen-2.5-coder-32b:free",
    "Skeptic3": "google/gemini-flash-1.5:free",
    "Volunteer": "mistralai/mistral-7b-instruct:free"
}

LOG_DIR = os.path.expanduser("~/hotseat_v2/logs")
os.makedirs(LOG_DIR, exist_ok=True)

def call_model(persona, prompt):
    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json"},
        json={
            "model": MODELS[persona],
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.9,
            "max_tokens": 400
        }
    )
    if resp.status_code == 200:
        return resp.json()["choices"][0]["message"]["content"]
    return f"Error: {resp.status_code}"

def run_hotseat(idea, volunteer_statement):
    transcript = []
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Skeptics speak
    skeptic_responses = {}
    for persona in ["Skeptic1", "Skeptic2", "Skeptic3"]:
        prompt = f"You are a ruthless skeptic. The idea: '{idea}'. The volunteer says: '{volunteer_statement}'. Tear it apart with brutal logic, sarcasm, and evidence. No mercy."
        response = call_model(persona, prompt)
        skeptic_responses[persona] = response
        transcript.append(f"**{persona}**: {response}")
        yield "\n\n".join(transcript) + "\n\n---\n\n*Processing next skeptic...*"
        time.sleep(1)
    
    # Volunteer responds
    prompt = f"As the volunteer, defend the idea '{idea}' against these critiques:\n" + "\n".join(skeptic_responses.values()) + "\n\nBe persuasive, use facts, and counter each point."
    volunteer_reply = call_model("Volunteer", prompt)
    transcript.append(f"**Volunteer**: {volunteer_reply}")
    yield "\n\n".join(transcript)
    
    # Save log
    log_file = os.path.join(LOG_DIR, f"hotseat_{timestamp}.json")
    with open(log_file, "w") as f:
        json.dump({"idea": idea, "volunteer_statement": volunteer_statement, "transcript": transcript}, f, indent=2)
    yield f"\n\n✅ Log saved to {log_file}"

with gr.Blocks(title="HotSeat v2") as demo:
    gr.Markdown("# 🔥 HotSeat v2 – No Mercy")
    with gr.Row():
        idea = gr.Textbox(label="Your Idea", lines=3)
        statement = gr.Textbox(label="Volunteer's Opening Statement", lines=3)
    run_btn = gr.Button("Start the HotSeat")
    output = gr.Markdown()
    run_btn.click(run_hotseat, inputs=[idea, statement], outputs=output)

if __name__ == "__main__":
    demo.launch(server_port=7860)
