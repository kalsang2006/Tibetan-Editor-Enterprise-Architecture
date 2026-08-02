import sys
from pathlib import Path

sys.path.insert(0, str(Path(".").resolve()))
sys.path.insert(0, str(Path("src").resolve()))

from teea.engine import TEEAEngine

text = """སློབ་བསྦྱོང་གིས་གལ་ནད་སྐོར་ཤད་པ།
དེང་འདུས་ཀྱིས་ཇིག་བརྟེན་འདིར་མི་ཚེ་སོན་པོར་གནས་པ་དང་འདུན་སྐྱོད་བྱེད་ཆེ་བསློབ་སྦྱོང་ནི་ཧ་བཅང་གལ་ཆེ་བ་ཞིག་ཡིན། སློབ་སྦྱོང་ཅེས་པ་ནི་དཔེ་དེབ་ཀྱིས་བཤེས་བྱ་ཁོ་ན་བཙམ་མིན་པར། མི་ཚེའི་ཟང་བསྤྱོད་དང་། མནུས་པ། ཡོན་བཏན་བཅས་ཡོངས་དུ་འཛོམས་པས་ལམ་བུ་ཅིགཡིན། མིའི་རིག་ལ་ཤེ་ཡོན་མེད་ན་མུན་མནག་ནང་ཏུ་རྒྱུ་བ་དང་འདྲའ་སྟེ། ཤེས་ཡོན་གྱི་ང་ཚོའི་བློ་བགྲོས་ཀྱིས་སྒོ་མོ་ཕྱེ་ཞིང་། བཟང་ངན་དང་། བླང་འདོར་གྱིས་ནས་ཚུལ་འབྱེད་པར་བྱེད། ལྷག་པར་དུ་ན་ཞོན་ཚོ་དུས་ཚོད་སེར་ལྟར་དུ་བརྩིས་དེ་སློབ་སྦྱོང་ལ་འབད་དགོས་པ་ཡིན། དེ་ཡང་སློབ་སྦྱོང་ལེག་པར་བྱས་ན། རང་ཉིད་ཀྱིས་མི་འཚེ་ཛེས་སྡུག་ལྡན་པ་ཞིག་བསྐྲུན་ཐུབ་པ་མ་ཟད། སྤྱི་ཚོག་དང་རྒྱལ་འཁབ་ཀྱི་ཞབ་ཞུ་སྒྲུབ་པའི་ནུས་པ་ཡང་ཆེན་པོ་ཐོན་གྱིས་ཡོད། མདོར་ན་སློབ་བྱོང་ནི་མི་ཚེའི་མརྒྱན་ཆ་ཆོག་རུ་གྱུར་པ་ཞིག་ཡིན་པའི། ང་ཚོས་མནམ་ཡང་སློབ་སྦྱོང་བྱེད་པར་མརྒྱུན་འཆད་མེ་པའི་བད་རྩོན་བྱེས་གོས།"""

print("=== ANALYZING USER'S PARAGRAPH ===")
engine = TEEAEngine()
unified = engine.analyze(text)

print(f"Total Suggestions Emitted: {len(unified.suggestions)}")
no_fix_count = 0

for i, s in enumerate(unified.suggestions, 1):
    if s.source == "teea.diagnostics":
        continue
    flagged = text[s.span.char_start:s.span.char_end]
    has_fix = s.replacement is not None
    if not has_fix:
        no_fix_count += 1
    print(f"\n{i}. [{s.priority.value.upper()}] source={s.source} err_type={s.error_type}")
    print(f"   Flagged:     '{flagged}' (chars {s.span.char_start}:{s.span.char_end})")
    print(f"   Replacement: '{s.replacement}' (Has Fix: {has_fix})")
    print(f"   Message:     {s.message}")

print(f"\nTotal Suggestions with NO FIX (replacement=None): {no_fix_count}")
