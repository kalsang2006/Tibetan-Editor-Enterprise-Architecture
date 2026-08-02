from fairseq import checkpoint_utils, tasks
import torch

# Load your model
model, cfg, task = checkpoint_utils.load_model_ensemble_and_task(
    ['models/tibert-grammar-correction-final/checkpoint_best.pt']
)
model[0].eval()

# The sentence with a [MASK] where the error is
sentence = 'ང་ཚོས [MASK] བྱ'

# Encode it
tokens = task.source_dictionary.encode_line(sentence, append_eos=True).unsqueeze(0)

# Find where the mask is
mask_idx = (tokens == task.source_dictionary.index('[MASK]')).nonzero(as_tuple=True)

# Create a boolean mask tensor
mask_tensor = torch.zeros_like(tokens, dtype=torch.bool)
mask_tensor[mask_idx] = True

# Run inference
with torch.no_grad():
    logits = model[0](tokens, mask=mask_tensor)[0]  # [0] because Fairseq returns (logits, extra)
    pred = logits[mask_idx].argmax(dim=-1)
    predicted_word = task.source_dictionary.string(pred).strip()

print(f"Original sentence: {sentence}")
print(f"Model suggests for [MASK]: {predicted_word}")