import sys
from pathlib import Path

ROOT = Path(r"c:\Users\kalsa\Desktop\Tibetan Editor Enterprise Architecture")
sys.path.insert(0, str(ROOT / "src"))

from teea.plagiarism.engine import PlagiarismEngine
from teea.plagiarism.models import FingerprintMatch
from teea.core.config import PlagiarismSettings
from teea.plagiarism.fingerprinting import normalize_and_fingerprint

def main():
    # Base source document (about 50 words)
    source_doc = (
        "༄༅། །བོད་སྐད་ནི་བོད་རིགས་ཀྱི་སྐད་ཡིག་ཡིན་ཞིང་། དེ་ནི་འཛམ་གླིང་སྟེང་གི་སྐད་ཡིག་རྙིང་ཤོས་ཤིག་རེད། "
        "བོད་སྐད་ལ་ལོ་རྒྱུས་ཡུན་རིང་ལྡན་པ་མ་ཟད། ནང་ཆོས་ཀྱི་གཞུང་ལུགས་མང་པོ་བོད་སྐད་དུ་བསྒྱུར་ཡོད། "
        "དེང་སང་བོད་སྐད་ནི་བོད་རང་སྐྱོང་ལྗོངས་དང་། མཚོ་སྔོན། ཀན་སུའུ། སི་ཁྲོན་སོགས་སུ་བེད་སྤྱོད་བྱེད་བཞིན་ཡོད། "
        "བོད་སྐད་སྦྱོང་རྒྱུ་ནི་བོད་ཀྱི་རིག་གནས་ལ་རྒྱུས་ལོན་བྱེད་པར་ཧ་ཅང་གལ་ཆེན་པོ་ཡིན།"
    )
    
    # 0% overlap
    doc_0 = "དེ་རིང་གནམ་གཤིས་ཧ་ཅང་ཡག་པོ་འདུག ང་ཚོ་ལྷ་སར་འགྲོ་རྒྱུ་ཡིན། པོ་ཏ་ལ་ལ་མཇལ་སྐོར་དུ་འགྲོ་དགོས། དེར་མི་མང་པོ་འདུག"
    
    # 25% overlap (Sentence 1 copied)
    doc_25 = (
        "༄༅། །བོད་སྐད་ནི་བོད་རིགས་ཀྱི་སྐད་ཡིག་ཡིན་ཞིང་། དེ་ནི་འཛམ་གླིང་སྟེང་གི་སྐད་ཡིག་རྙིང་ཤོས་ཤིག་རེད། "
        "དེ་རིང་གནམ་གཤིས་ཧ་ཅང་ཡག་པོ་འདུག ང་ཚོ་ལྷ་སར་འགྲོ་རྒྱུ་ཡིན། པོ་ཏ་ལ་ལ་མཇལ་སྐོར་དུ་འགྲོ་དགོས།"
    )

    # 50% overlap (Sentences 1 and 2 copied)
    doc_50 = (
        "༄༅། །བོད་སྐད་ནི་བོད་རིགས་ཀྱི་སྐད་ཡིག་ཡིན་ཞིང་། དེ་ནི་འཛམ་གླིང་སྟེང་གི་སྐད་ཡིག་རྙིང་ཤོས་ཤིག་རེད། "
        "བོད་སྐད་ལ་ལོ་རྒྱུས་ཡུན་རིང་ལྡན་པ་མ་ཟད། ནང་ཆོས་ཀྱི་གཞུང་ལུགས་མང་པོ་བོད་སྐད་དུ་བསྒྱུར་ཡོད། "
        "ང་ཚོ་ལྷ་སར་འགྲོ་རྒྱུ་ཡིན། པོ་ཏ་ལ་ལ་མཇལ་སྐོར་དུ་འགྲོ་དགོས།"
    )
    
    # 75% overlap (Sentences 1, 2, 3 copied)
    doc_75 = (
        "༄༅། །བོད་སྐད་ནི་བོད་རིགས་ཀྱི་སྐད་ཡིག་ཡིན་ཞིང་། དེ་ནི་འཛམ་གླིང་སྟེང་གི་སྐད་ཡིག་རྙིང་ཤོས་ཤིག་རེད། "
        "བོད་སྐད་ལ་ལོ་རྒྱུས་ཡུན་རིང་ལྡན་པ་མ་ཟད། ནང་ཆོས་ཀྱི་གཞུང་ལུགས་མང་པོ་བོད་སྐད་དུ་བསྒྱུར་ཡོད། "
        "དེང་སང་བོད་སྐད་ནི་བོད་རང་སྐྱོང་ལྗོངས་དང་། མཚོ་སྔོན། ཀན་སུའུ། སི་ཁྲོན་སོགས་སུ་བེད་སྤྱོད་བྱེད་བཞིན་ཡོད། "
        "ང་ཚོ་ལྷ་སར་འགྲོ་རྒྱུ་ཡིན།"
    )

    # 100% overlap
    doc_100 = source_doc

    docs = [
        ("0%", doc_0),
        ("25%", doc_25),
        ("50%", doc_50),
        ("75%", doc_75),
        ("100%", doc_100)
    ]

    engine = PlagiarismEngine(settings=PlagiarismSettings())
    
    # Generate fingerprints for the source document
    _, fps = normalize_and_fingerprint(
        source_doc,
        kgram_size=engine.settings.kgram_size,
        winnow_window=engine.settings.winnow_window,
        normalization_form=engine.settings.normalization_form,
    )
    from teea.plagiarism.fingerprinting import hash_set
    from teea.plagiarism.models import SourceDocument
    
    doc_hashes = hash_set(fps)
    src_document = SourceDocument(
        document_id="source_doc_1",
        source=source_doc,
        fingerprints=doc_hashes
    )
    
    engine.index.add(src_document)
    
    for name, text in docs:
        result = engine.detect(text)
        if result.matches:
            match = result.matches[0]
            pct = round(match.similarity * 100)
            print(f"{name} text -> Detected {pct}% overlap")
        else:
            print(f"{name} text -> Detected 0% overlap")

if __name__ == "__main__":
    main()
