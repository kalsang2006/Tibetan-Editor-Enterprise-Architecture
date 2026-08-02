from teea.corpus.repository import BoCorpusRepository

corpus = BoCorpusRepository()
if corpus.is_available():
    print(f"Bigram freq 'བཀྲ ཤེས': {corpus.bigrams.get('བཀྲ ཤེས', 0)}")
    print(f"Bigram freq 'བཀྲ་ ཤེས་': {corpus.bigrams.get('བཀྲ་ ཤེས་', 0)}")
    print(f"Freq 'བཀྲ་ཤེས': {corpus.get_syllable_frequency('བཀྲ་ཤེས')}")
    print(f"Freq 'བཀྲ་ཤིས': {corpus.get_syllable_frequency('བཀྲ་ཤིས')}")
