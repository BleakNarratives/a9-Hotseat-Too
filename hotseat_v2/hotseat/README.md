# The Hot Seat

Three voices. One idea. No survivors.

"The Hot Seat" is a local-first idea stress-testing system built for Android/Termux. It uses local LLMs (via Ollama) to provide three distinct perspectives on any idea or project.

## The Voices

- **Dame Audrey Blackwell-Finch**: A snippy British auditor who identifies what's broken and why.
- **Claiborne von Billingsley III (Claib)**: A trust fund Burning Man bro who looks 3 steps ahead at the market.
- **Vertical AI**: A concise, direct voice that speaks the hard truth Michael needs to hear.

## Installation

1.  **Ollama**: Ensure Ollama is running locally:
    ```bash
    ollama serve &
    ```
2.  **Models**: Ensure you have the required models:
    - `zane-preacher:latest` (Audrey)
    - `llama3.2:1b` (Claib)
    - `deepseek-coder:latest` (Vertical)
3.  **Dependencies**:
    ```bash
    pip install requests websockets --break-system-packages
    ```

## Usage

- **Interactive Mode**:
    ```bash
    python hotseat.py
    ```
- **Direct Mode**:
    ```bash
    python hotseat.py "Your brilliant idea here"
    ```
- **WebSocket Server**:
    ```bash
    python hotseat.py --ws
    ```

## Structure

- `hotseat.py`: Main entry point and logic.
- `memory.db`: SQLite database for session history.
- `sessions.log`: Append-only log of topics.
