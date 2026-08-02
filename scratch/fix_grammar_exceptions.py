import pathlib

p = pathlib.Path(r"src\teea\plugins\builtin\grammar.py")
content = p.read_text("utf-8")

old_block = (
    '#: Curated exception list for common proper nouns, loanwords, and religious terms.\n'
    '_CURATED_EXCEPTIONS = frozenset({\n'
    '    "\u0f62\u0fa1\u0f7c\u0f0b\u0f62\u0f97\u0f7a", "\u0f46\u0f7c\u0f66\u0f0b\u0f63\u0f74\u0f42\u0f66", "\u0f66\u0f44\u0f66\u0f0b\u0f62\u0f92\u0fb1\u0f66", "\u0f68\u0f7c\u0f7e", "\u0f54\u0f51\u0fa8", "\u0f56\u0f40\u0fb2\u0f0b\u0f64\u0f72\u0f66\u0f0b\u0f56\u0f51\u0f7a\u0f0b\u0f63\u0f7a\u0f42\u0f66", "\u0f63\u0fb7\u0f0b\u0f66",\n'
    '    "\u0f4f\u0f71\u0f0b\u0f63\u0f60\u0f72", "\u0f56\u0fb3\u0f0b\u0f58", "\u0f62\u0f72\u0f53\u0f0b\u0f54\u0f7c\u0f0b\u0f46\u0f7a", "\u0f60\u0f55\u0f42\u0f66\u0f0b\u0f54",\n'
    '})'
)

new_block = (
    '#: Curated exception list for common proper nouns, loanwords, and religious terms.\n'
    '#: Lexical rules (TIB-VOWEL-001, TIB-CHAR-001) skip these to avoid false positives.\n'
    '_CURATED_EXCEPTIONS = frozenset({\n'
    '    # Religious / Buddhist terms\n'
    '    "\u0f62\u0fa1\u0f7c\u0f0b\u0f62\u0f97\u0f7a", "\u0f46\u0f7c\u0f66\u0f0b\u0f63\u0f74\u0f42\u0f66", "\u0f66\u0f44\u0f66\u0f0b\u0f62\u0f92\u0fb1\u0f66", "\u0f68\u0f7c\u0f7e", "\u0f54\u0f51\u0fa8",\n'
    '    "\u0f56\u0f40\u0fb2\u0f0b\u0f64\u0f72\u0f66\u0f0b\u0f56\u0f51\u0f7a\u0f0b\u0f63\u0f7a\u0f42\u0f66", "\u0f63\u0fb7\u0f0b\u0f66", "\u0f4f\u0f71\u0f0b\u0f63\u0f60\u0f72", "\u0f56\u0fb3\u0f0b\u0f58",\n'
    '    "\u0f62\u0f72\u0f53\u0f0b\u0f54\u0f7c\u0f0b\u0f46\u0f7a", "\u0f60\u0f55\u0f42\u0f66\u0f0b\u0f54", "\u0f51\u0f54\u0f63", "\u0f42\u0f5f\u0f72\u0f42\u0f66",\n'
    '    "\u0f56\u0f7c\u0f51\u0f72\u0f0b\u0f66\u0f4f\u0fa1", "\u0f58\u0f44\u0f7c\u0f53\u0f0b\u0f54\u0f7c",\n'
    '    # Sanskrit loanwords\n'
    '    "\u0f51\u0f40\u0f60", "\u0f51\u0f40\u0f60\u0f0b\u0f56\u0f62\u0fa9\u0f7a\u0f42\u0f66", "\u0f56\u0f7c\u0f51\u0fb7\u0f72\u0f0b\u0f66\u0f4f\u0fa1",\n'
    '    # Place names\n'
    '    "\u0f62\u0f92\u0fb1\u0f0b\u0f53\u0f42", "\u0f62\u0f92\u0fb1\u0f0b\u0f42\u0f62",\n'
    '})'
)

if old_block in content:
    content = content.replace(old_block, new_block)
    p.write_text(content, "utf-8")
    print("SUCCESS: grammar exception list expanded")
else:
    print("NOT FOUND - dumping lines 107-111:")
    lines = p.read_text("utf-8").splitlines()
    for i in range(106, min(112, len(lines))):
        print(f"  L{i+1}: {repr(lines[i])}")
