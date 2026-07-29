import sys
import os
import json

sys.path.insert(0, os.path.abspath('src'))
from transformers import AutoTokenizer

t = AutoTokenizer.from_pretrained('CMLI-NLP/TiBERT')
enc1 = t('ང་བཀྲ་ཤམ་ཟེར།', return_offsets_mapping=True)
enc2 = t('ང་བཀྲ་ཤིས་ཟེར།', return_offsets_mapping=True)

out = {
    'sham': {
        'tokens': t.convert_ids_to_tokens(enc1['input_ids']),
        'offsets': enc1['offset_mapping']
    },
    'shis': {
        'tokens': t.convert_ids_to_tokens(enc2['input_ids']),
        'offsets': enc2['offset_mapping']
    }
}

with open('tokens.json', 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
