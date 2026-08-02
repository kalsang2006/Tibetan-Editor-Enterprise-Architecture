import json
from teea.engine import TEEAEngine
engine = TEEAEngine()

# Get the plugin
spell_plugin = None
for p in engine._plugins:
    if p.name == "teea.spelling":
        spell_plugin = p
        break

snapshot = engine._builder.analyze('བཀྲ་ཤེས་བདེ་ལེགས།')
suggestions = list(spell_plugin.examine(snapshot))

out = {
    "suggestions": [s.model_dump() for s in suggestions]
}

with open('scratch/debug_plugin.json', 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
