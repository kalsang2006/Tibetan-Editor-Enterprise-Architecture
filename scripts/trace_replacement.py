import unicodedata

def hex_cp(text: str) -> str:
    return " ".join([f"{c} (U+{ord(c):04X})" for c in text])

def trace():
    print("--- TRACE ---")
    doc_before = "ང་བཀྲ་ཤིམ་ཟེར།"
    target_word = "ཤིམ"
    
    # Simulating what happened: The spell checker extracted "ཤིམ" (no tsek)
    # The winning candidate was "ཤི་" (sha + gigu + tsek)
    winning_candidate = "ཤི་"
    
    doc_after = doc_before.replace(target_word, winning_candidate)
    
    print("1. Candidate string before replacement (original extracted word):")
    print(f"   String: '{target_word}'")
    print(f"   Code points: {hex_cp(target_word)}")
    print()
    
    print("2. Exact replacement string (winning candidate):")
    print(f"   String: '{winning_candidate}'")
    print(f"   Code points: {hex_cp(winning_candidate)}")
    print()
    
    print("3. Unicode code points of the replacement:")
    print(f"   {hex_cp(winning_candidate)}")
    print()
    
    print("4. The replacement range (simulated based on Word Add-in):")
    start = doc_before.find(target_word)
    end = start + len(target_word)
    print(f"   Indices: {start} to {end}")
    print()
    
    print("5. Document text before Apply:")
    print(f"   String: '{doc_before}'")
    print(f"   Code points: {hex_cp(doc_before)}")
    print()
    
    print("6. Document text after Apply:")
    print(f"   String: '{doc_after}'")
    print(f"   Code points: {hex_cp(doc_after)}")
    print()
    
    print("--- ROOT CAUSE ANALYSIS ---")
    print("The exact character causing the corruption is U+0F0B (TIBETAN MARK INTERSYLLABIC TSHEG) inside the winning candidate 'ཤི་'.")
    print("Because the tokenizer extracted 'ཤིམ' without a trailing tsheg, the candidates were compared against 'ཤིམ'.")
    print("'ཤི་' (U+0F64 U+0F72 U+0F0B) has a Levenshtein distance of 1 from 'ཤིམ' (U+0F64 U+0F72 U+0F58) because U+0F58 (མ) is replaced by U+0F0B (་).")
    print("TiBERT scored 'ཤི་' higher than 'ཤིས'. When 'ཤི་' (which ends with a tsheg) is inserted before the existing right context '་ཟེར།' (which starts with a tsheg), it results in a double tsheg '་' + '་'.")
    print("The trailing 'ས' is missing because the winning candidate was 'ཤི་', not 'ཤིས' or 'ཤིས་'.")

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    trace()
