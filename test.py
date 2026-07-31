"""Check Tibetan text for spelling and grammar errors using TEEA."""
import sys
sys.path.insert(0, "src")

from teea.engine import TEEAEngine

# Replace this with any Tibetan text you want to check
TEXT = "བཀྲ་ཤིང་བདེ་ལེགས། ང་དཔེ་ཆ་ཀློག་པ་ཡོད། ཁོང་ཡི་གེ་འབྲི་ཡི་འདུག།"

engine = TEEAEngine()
results = engine.analyze(TEXT)

print(f"Input text: {TEXT}\n")
print(f"Total suggestion groups: {len(results)}\n")

for group in results:
    # group is a tuple like ('suggestions', (Suggestion, ...))
    _, suggestions = group  # suggestions is a tuple of Suggestion objects
    for sug in suggestions:
        print("---")
        print(f"Source: {sug.source}")
        print(f"Error type: {sug.error_type}")
        print(f"Message: {sug.message}")
        # Some suggestions have a 'replacement' field instead of 'word'
        if sug.replacement:
            print(f"Replacement: {sug.replacement}")
        # If the suggestion has a 'word' attribute (spelling suggestions)
        if hasattr(sug, 'word'):
            print(f"Word: {sug.word}")
        if hasattr(sug, 'candidates'):
            print(f"Candidates: {sug.candidates}")
        print(f"Score: {sug.score:.2f}, Priority: {sug.priority}")