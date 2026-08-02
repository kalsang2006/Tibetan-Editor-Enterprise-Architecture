/**
 * Proof of the root cause behind "Original text no longer holds at specified range".
 *
 * The daemon computes char offsets relative to the EXACT text the pane sent it.
 * `readDocumentText` tier 1 (`getFileAsync(Office.FileType.Text)`) returns
 * paragraph breaks as `\r\n` on Windows, but `applyOperations` reconstructs
 * document offsets by assuming every paragraph boundary is exactly ONE
 * character (`totalDocLength += pLen + 1`). Every paragraph after the first
 * therefore shifts by 1 char per boundary — enough to make the 6-char
 * verification fail for the whole batch.
 *
 * Run: node scratch/apply_offset_proof.js
 */
const paragraphs = [
  'བཀྲ་ཤིས་བདེ་ལེགས། ཚེས་གཅིག་གི་ཉིན་མོ་རེད།',
  'ང་ཚོས་ཡིག་ཆ་ཀློག་པ་དང་། རྩོམ་ཡིག་བྲིས།',
  'དེ་རྗེས་སློབ་གྲྭར་སོང་ནས་སློབ་སྦྱོང་བྱས།',
];

// --- What readDocumentText (tier 1, Windows) sends the daemon ---------------
const analysisText = paragraphs.join('\r\n'); // CRLF paragraph breaks

// A suggestion the daemon emits for text in paragraph index 2:
const target = 'སློབ་སྦྱོང';
const daemonOffset = analysisText.indexOf(target);

// --- How applyOperations reconstructs offsets (1 char per boundary) ----------
let total = 0;
const spans = [];
for (const p of paragraphs) {
  spans.push({ start: total, end: total + p.length, text: p });
  total += p.length + 1; // <-- assumes exactly ONE separator char
}
const span = spans.find((s) => daemonOffset >= s.start && daemonOffset <= s.end);
const local = daemonOffset - span.start;
const actual = span.text.slice(local, local + target.length);

console.log('=== BEFORE FIX: analysis text uses CRLF, apply assumes 1-char separators ===');
console.log(`daemon offset of "${target}": ${daemonOffset}`);
console.log(`apply resolves to:          "${actual}"`);
console.log(`verification passes?        ${actual === target ? 'YES' : 'NO  <-- all ops skipped'}`);
const drift = paragraphs.slice(0, spans.indexOf(span)).length; // boundaries before target
console.log(`drift: ${drift} char(s) (1 per preceding paragraph boundary)\n`);

// --- AFTER FIX: readDocumentText canonicalizes separators to \r --------------
const canonicalText = analysisText.replace(/\r\n/g, '\r').replace(/\n/g, '\r');
const canonicalOffset = canonicalText.indexOf(target);
const span2 = spans.find((s) => canonicalOffset >= s.start && canonicalOffset <= s.end);
const local2 = canonicalOffset - span2.start;
const actual2 = span2.text.slice(local2, local2 + target.length);

console.log('=== AFTER FIX: analysis text canonicalized to CR (matches apply math) ===');
console.log(`daemon offset of "${target}": ${canonicalOffset}`);
console.log(`apply resolves to:          "${actual2}"`);
console.log(`verification passes?        ${actual2 === target ? 'YES <-- fix works' : 'NO'}`);
