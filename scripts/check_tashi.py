import sys
import os
import json
sys.path.insert(0, os.path.abspath('src'))
from transformers import AutoTokenizer

t = AutoTokenizer.from_pretrained('CMLI-NLP/TiBERT')
enc = t('བཀྲ་ཤིས་')
tokens = t.convert_ids_to_tokens(enc['input_ids'])
ids = enc['input_ids']

with open('tashi_tokens.json', 'w', encoding='utf-8') as f:
    json.dump({'tokens': tokens, 'ids': ids}, f, ensure_ascii=False, indent=2)
