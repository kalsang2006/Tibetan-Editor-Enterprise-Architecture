import sys
import os
import json

sys.path.insert(0, os.path.abspath('src'))
from transformers import AutoTokenizer

t = AutoTokenizer.from_pretrained('CMLI-NLP/TiBERT')
enc = t('ང་བཀྲ་[MASK]་ཟེར།', return_offsets_mapping=True)

out = {
    'mask': {
        'tokens': t.convert_ids_to_tokens(enc['input_ids']),
        'offsets': enc['offset_mapping']
    }
}

with open('mask_tokens.json', 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
