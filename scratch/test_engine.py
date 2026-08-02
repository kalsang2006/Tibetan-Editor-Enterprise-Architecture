from teea.engine import TEEAEngine
engine = TEEAEngine()
unified = engine.analyze("བཀྲ་ཤེས་བདེ་ལེགས།")
with open("scratch/test_engine_out.json", "w", encoding="utf-8") as f:
    f.write(unified.model_dump_json(indent=2))
