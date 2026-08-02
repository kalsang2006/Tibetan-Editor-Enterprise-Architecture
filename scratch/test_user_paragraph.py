import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from teea.engine import TEEAEngine

def analyze_user_paragraph():
    sys.stdout.reconfigure(encoding="utf-8")
    text = """སློབ་བསྦྱོང་གིས་གལ་ནད་སྐོར་ཤད་པ།

དེང་འདུས་ཀྱིས་ཇིག་བརྟེན་འདིར་མི་ཚེ་སོན་པོར་གནས་པ་དང་འདུན་སྐྱོད་བྱེད་ཆེ་བསློབ་སྦྱོང་ནི་ཧ་བཅང་གལ་ཆེ་བ་ཞིག་ཡིན། སློབ་སྦྱོང་ཅེས་པ་ནི་དཔེ་དེབ་ཀྱིས་བཤེས་བྱ་ཁོ་ན་བཙམ་མིན་པར། མི་ཚེའི་ཟང་བསྤྱོད་དང་། མནུས་པ། ཡོན་བཏན་བཅས་ཡོངས་དུ་འཛོམས་པས་ལམ་བུ་ཅིགཡིན། མིའི་རིག་ལ་ཤེ་ཡོན་མེད་ན་མུན་མནག་ནང་ཏུ་རྒྱུ་བ་དང་འདྲའ་སྟེ། ཤེས་ཡོན་གྱི་ང་ཚོའི་བློ་བགྲོས་ཀྱིས་སྒོ་མོ་ཕྱེ་ཞིང་། བཟང་ངན་དང་། བླང་འདོར་གྱིས་ནས་ཚུལ་འབྱེད་པར་བྱེད། ལྷག་པར་དུ་ན་ཞོན་ཚོ་དུས་ཚོད་སེར་ལྟར་དུ་བརྩིས་དེ་སློབ་སྦྱོང་ལ་འབད་དགོས་པ་ཡིན། དེ་ཡང་སློབ་སྦྱོང་ལེག་པར་བྱས་ན། རང་ཉིད་ཀྱིས་མི་འཚེ་ཛེས་སྡུག་ལྡན་པ་ཞིག་བསྐྲུན་ཐུབ་པ་མ་ཟད། སྤྱི་ཚོག་དང་རྒྱལ་འཁབ་ཀྱི་ཞབ་ཞུ་སྒྲུབ་པའི་ནུས་པ་ཡང་ཆེན་པོ་ཐོན་གྱིས་ཡོད། མདོར་ན་སློབ་བྱོང་ནི་མི་ཚེའི་མརྒྱན་ཆ་ཆོག་རུ་གྱུར་པ་ཞིག་ཡིན་པའི། ང་ཚོས་མནམ་ཡང་སློབ་སྦྱོང་བྱེད་པར་མརྒྱུན་འཆད་མེ་པའི་བད་རྩོན་བྱེས་གོས།"""
    
    print("=" * 80)
    print("ANALYZING USER'S TIBETAN PARAGRAPH FROM MICROSOFT WORD:")
    print("=" * 80)
    engine = TEEAEngine()
    result = engine.analyze(text)
    items = result.suggestions
    print(f"[✓] TEEA Engine Analysis Complete! Detected {len(items)} issues:")
    print("-" * 80)
    for i, s in enumerate(items, 1):
        if s.source == "teea.diagnostics":
            continue
        token = text[s.span.char_start:s.span.char_end]
        print(f" {i:2d}. [{s.source:<12}] '{token}' -> '{s.replacement}'")
        print(f"     Message: {s.message}")

if __name__ == "__main__":
    analyze_user_paragraph()
