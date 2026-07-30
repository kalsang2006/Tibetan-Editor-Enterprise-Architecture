# 📚 TEEA Data & Rule Maintenance Guide

This document explains how non-developer domain experts, Tibetan linguists, and system maintainers can extend and update TEEA's spelling, grammar, and structural rules without modifying Python source code.

---

## 1. Dynamic Confusion Sets (`Data/Processed/confusion_sets.json`)

The system loads `confusion_sets.json` at startup to automatically catch dialectal misspellings, real-word homophone errors, and compound typos.

### Structure

```json
{
  "confusion_dict": {
    "དེང་འདུས": ["དེང་དུས"],
    "འཇིག་བརྟེན": ["འཇིག་རྟེན"],
    "འདུན་སྐྱོད": ["མདུན་བསྐྱོད"],
    "བསླབ་སྦྱོང": ["སློབ་སྦྱོང"],
    "བཙམ": ["ཙམ"],
    "བཟང་བསྐྱོད": ["བཟང་སྤྱོད"],
    "ཡོངས་དུ": ["ཡོངས་སུ"],
    "རིག་ལ": ["རིགས་ལ"],
    "ཤེ་ཡོན": ["ཤེས་ཡོན"],
    "མུན་མནག": ["མུན་ནག"],
    "བློ་བགྲོས": ["བློ་གྲོས"],
    "ན་ཞོན": ["ན་གཞོན"],
    "སེར་ལྟར": ["གསེར་ལྟར"],
    "མི་འཚེ": ["མི་ཚེ"],
    "ཛེ་སྡུག": ["མཛེས་སྡུག"],
    "སྤྱི་ཚོག": ["སྤྱི་ཚོགས"],
    "རྒྱལ་འཁོབ": ["རྒྱལ་ཁབ"],
    "མརྒད་ཆ": ["རྒྱན་ཆ"],
    "ཆོག་རུ": ["མཆོག་ཏུ"],
    "མནམ": ["ནམ"],
    "བད་རྩོན": ["འབད་བརྩོན"],
    "བྱེས་གོས": ["བྱེད་དགོས"]
  },
  "phonetic": [
    ["ཀ", "ག"],
    ["ཅ", "ཇ"]
  ],
  "visual": [
    ["ཏ", "ད"],
    ["ན", "མ"]
  ],
  "orthographic": [
    ["གི", "ཀྱི"],
    ["དག", "བག"]
  ]
}
```

### How to Add New Error Patterns
To add a new common typo or dialectal error:
1. Open `Data/Processed/confusion_sets.json`.
2. Add the corrupted phrase as the **key** and the list containing the correct phrase as the **value**:
   ```json
   "corrupted_word": ["correct_word"]
   ```
3. Save the file and restart the daemon. The engine will pick up the new rule automatically.

---

## 2. Vocabulary & Dictionary Extensions (`Data/Processed/bocorpus_vocabulary.json`)

To add new technical terms, proper nouns, or valid Tibetan vocabulary:
1. Open `Data/Processed/bocorpus_vocabulary.json`.
2. Add the word key with its occurrence frequency:
   ```json
   "གསར་འགྱུར": 1500
   ```
3. The spellcheck plugin (`SpellCheckerPlugin`) and candidate provider (`CorrectionProvider`) will immediately recognize the word as valid and use its frequency for edit-distance ranking (`score = distance - log(frequency)`).

---

## 3. Feedback Logging & Continuous Learning

When users interact with suggestions in the Word Add-in (accepting or dismissing edits), the daemon logs feedback entries. 

* Accepted edits are appended to `Data/Processed/user_feedback.json`.
* Periodically, a maintainer can run `python scripts/merge_feedback.py` to fold accepted user corrections directly into `confusion_sets.json`.
