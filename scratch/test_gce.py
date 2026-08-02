import sys
from pathlib import Path

# Reconfigure stdout for UTF-8 on Windows
sys.stdout.reconfigure(encoding="utf-8")

# Add src directory to Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# Importing the Grammar Correction Engine
from teea.ai.grammar_correction_engine import GrammarCorrectionEngine as OHEMSGECFUCK

# Model path definition
put_the_model_path_im_gonna_tell_you = "./models/tibert-grammar-correction-final"

the_engine_instance = OHEMSGECFUCK(model_path=put_the_model_path_im_gonna_tell_you)

if the_engine_instance.is_available():
    print("THE MODEL IS LOADING CORRECTLY YAAYAAYAY")
else:
    print("WOMP WOMP WE FUCKED UP NIGGA")

# Tibetan test sentences provided by user
test_stuff = [
    "ང་ཚོས བོང བྱ",
    "མི བྱས",
    "གལ་ཆེན ཡོད"
]

# ______ INFERENCE _____ (it should infer)
print("\n" + "="*50)
print("RUNNING INFERENCE")
print("="*50 + "\n")

for sentence in test_stuff:
    correct_sentence_we_get_back = the_engine_instance.correct(sentence=sentence)
    print("YO OHEM LOOK THIS IS THE ORIGINAL SENTENCE: ")
    print(sentence)
    print("YO OHEM LOOK THIS IS THE CORRECTED SENTENCE FUCK YEAHHHH")
    print(correct_sentence_we_get_back)
    print("-" * 50)
