from teea.engine import TEEAEngine

clean_essay = "གནད་དོན་འདི་བཤད་པར་བྱའོ། འཇིག་རྟེན་གསོན་པོའི་དཔེ་དེབ་ཤེས་རིག་བཟང་པོ་འདི་ཡིས་ནུས་པ་གཏན་ཏན་ཐོན་ནོ།"
engine = TEEAEngine()
unified = engine.analyze(clean_essay)
edits = [s for s in unified.suggestions if s.replacement is not None]
print(f"Total edits on clean essay: {len(edits)}")
for s in edits:
    print(f" - [{s.source}] {s.message} (span={s.span}, repl={s.replacement})")
