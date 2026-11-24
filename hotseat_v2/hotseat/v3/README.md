# V3 COMMAND INTERFACE DOCUMENTATION

## 1. SYSTEM OVERVIEW
This is a minimalist, two-tier architecture designed for direct command-line deployment. 
It bypasses the need for complex IDEs or build tools.

- **Backend (`app.py`):** A Python-based FastAPI server that acts as a bridge between your local file system and the web interface.
- **Frontend (`index.html`):** A standalone HTML/JavaScript dashboard that provides a visual interface for directory scanning.

---

## 2. COMPONENT BREAKDOWN

### A. The Backend (Python/FastAPI)
- **Host:** 0.0.0.0 (Accessible across local network devices)
- **Port:** 8000
- **Endpoint:** `/list/{dir_name}`
  - **Action:** Scans the folder provided in the URL.
  - **Security:** Implements CORS (Cross-Origin Resource Sharing) to allow the frontend to communicate without browser blocks.

### B. The Frontend (HTML/JS)
- **Technology:** Vanilla JavaScript (ES6 Fetch API).
- **Mechanism:** Captures user input, sends a GET request to the local API, and renders the directory manifest dynamically.

---

## 3. INSTALLATION & EXECUTION

### Step 1: Dependencies
Ensure your environment has the necessary Python libraries:
`pip install fastapi uvicorn`

### Step 2: Launching the Engine
Run the backend server:
`python3 app.py`

### Step 3: Accessing the Dashboard
Open `index.html` in any web browser. 
If running on a remote device (like a phone/Termux), use the device's IP address (e.g., `http://192.168.1.x:8000/list/your_folder`).

---

## 4. TROUBLESHOOTING
- **Connection Refused:** Ensure the backend is running. Check if port 8000 is occupied.
- **Empty Results:** Ensure the directory name entered in the dashboard exists in the same folder as `app.py`.
- **Permission Denied:** If running in a restricted environment, ensure the terminal has "Storage" permissions to read the local directories.
