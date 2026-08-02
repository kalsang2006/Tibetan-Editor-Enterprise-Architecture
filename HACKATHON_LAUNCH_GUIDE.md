# TEEA HACKATHON QUICK LAUNCH GUIDE

For the Live Hackathon Demonstrator / Presenter:

### 1. Launch TEEA Backend Daemon (Terminal 1)
```bash
python start_daemon.py
```
*Wait 3 seconds for `TEEA Daemon is active and serving complete HTTP+AI bridge at http://127.0.0.1:50505`.*

### 2. Launch Microsoft Word Add-in (Terminal 2)
```bash
cd addin
npm start
```
*Microsoft Word will open automatically with the **TEEA Tibetan Editor** tab loaded.*

### 3. (Alternative) Standalone Web UI Testing
If presenting without MS Word, open `local_ui/index.html` directly in Chrome or Edge to test real-time spelling, grammar correction, and plagiarism detection.

---

### Key Demo Inputs for Maximum Visual Impact:

- **Syllable Order Correction**: Type `གསུང་སྒོརབ་མཛོད་རིན་པོ་ཆེའི་གླེགས་བམ།` -> Accept suggestion -> Corrects to `གསུང་རབ་སྒོ་མཛོད་རིན་པོ་ཆེའི་གླེགས་བམ།`.
- **Duplicate Word Trim**: Type `སྲིད་པའི་མཛོད་ཕུགསཕུགས།` -> Accept suggestion -> Trims to `སྲིད་པའི་མཛོད་ཕུགས།`.
- **QLoRA Particle Agreement**: Type `དེ་ཡང་ཐར་བྱེད་འགྲོ་བ་འདུཀྱིས་བའི་བོན།` -> Accept suggestion -> Corrects to `དེ་ཡང་ཐར་བྱེད་འགྲོ་བ་འདུལ་བའི་བོན།`.
