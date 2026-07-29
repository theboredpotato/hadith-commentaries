#!/usr/bin/env python3
"""
fix_hadith_numbers.py
======================
Patches hadith_numbers into bab-*.json files that already exist on disk
(from bukhari_processor.py or manual splitting) WITHOUT re-splitting or
re-writing the .txt files. Much cheaper than re-running the full pipeline
since it only reads small text files and rewrites small JSON files.

USAGE
-----
    python3 fix_hadith_numbers.py <root_dir>

Example, matching your folder layout (data/fath_al_bari/book-32-book32 ...):
    python3 fix_hadith_numbers.py data/fath_al_bari

It walks every book-* folder under <root_dir>, reads each bab-*.txt, and
updates the matching bab-*.json's "hadith_numbers" field. It does NOT touch
bab_title, book, commentary_file, or verified — only hadith_numbers.

WHY THIS HAPPENED
------------------
The original script's list of recognized narration-opener words (حدثنا،
أخبرنا، وقال، etc.) was built from books 1-13. Later books cover very
different fiqh topics and very likely use citation phrasing that list never
saw. Rather than guess forever at new individual words, this version adds a
SECOND, more general pass: for any bab that still comes back with zero
hadith numbers after the known-verb pass, it also tries a broader catch-all
pattern (any number at the start of a paragraph, followed by a dash) — but
ONLY accepts a catch-all match if the number is plausible given the
neighboring babs' numbers (i.e. it's not wildly smaller than what came
right before it in sequence). This guards against the catch-all
accidentally grabbing something that ISN'T a hadith number, such as a bab
heading that omits the word "باب" (a real case found in Book 10, where a
line like "٦٥ - من أخف الصلاة..." looks number-dash-shaped but is a bab
number, not a hadith number).

REPORT
------
For every bab, one of three things happens, and the script tells you which:
  - "verb match"     — found via the known narration-opener list. Trusted.
  - "fallback match" — found via the catch-all, passed the plausibility
                        check. Probably fine, but double-check a couple of
                        these by eye before fully trusting them.
  - "STILL EMPTY"    — nothing found at all. Paste the first few hundred
                        characters of this bab's .txt file so the actual
                        opener word can be identified and added properly,
                        rather than guessing blind.

At the end it also prints, per book, the overall hadith range found and any
internal gaps/cross-bab duplicates — same checks as before.
"""

import sys
import os
import re
import json
import glob
from collections import Counter

AR_DIGITS = "٠١٢٣٤٥٦٧٨٩"


def ar_to_int(s: str) -> int:
    return int("".join(str(AR_DIGITS.index(c)) if c in AR_DIGITS else c for c in s))


# Known narration-openers accumulated across books 1-13.
CORE_VERBS = r"(?:حدث|أخبر|قال|زاد|سأل|كان|عن|بإسناده|أن|لو|رواه)"

VERB_PATTERN = re.compile(
    r"(?:^|\n)\s*([٠-٩]+)(?:\s*[،و]\s*([٠-٩]+))?\s*-?\s*(?:ثم\s*)?(?:و?"
    + CORE_VERBS
    + r"|«)"
)

# Broader catch-all: any number at the start of a paragraph followed by a
# dash, regardless of what comes after. Used only as a fallback, and only
# for numbers that pass the plausibility filter below.
FALLBACK_PATTERN = re.compile(r"(?:^|\n\n)\s*([٠-٩]+)(?:\s*[،و]\s*([٠-٩]+))?\s*-\s*")


def extract_verb_matches(body: str):
    seen = []
    for m in VERB_PATTERN.finditer(body):
        n1 = ar_to_int(m.group(1))
        if n1 not in seen:
            seen.append(n1)
        if m.group(2):
            n2 = ar_to_int(m.group(2))
            if n2 not in seen:
                seen.append(n2)
    return seen


def extract_fallback_matches(body: str, plausible_min: int):
    """Only keep numbers >= plausible_min (a floor based on neighboring
    babs) so a stray bab-number-shaped line doesn't get mistaken for a
    hadith number."""
    seen = []
    for m in FALLBACK_PATTERN.finditer(body):
        n1 = ar_to_int(m.group(1))
        if n1 >= plausible_min and n1 not in seen:
            seen.append(n1)
        if m.group(2):
            n2 = ar_to_int(m.group(2))
            if n2 >= plausible_min and n2 not in seen:
                seen.append(n2)
    return seen


def process_book_folder(book_dir):
    bab_files = sorted(glob.glob(os.path.join(book_dir, "bab-*.json")))
    if not bab_files:
        return

    print(f"\n=== {os.path.basename(book_dir)} ===")

    running_max = 0  # tracks the highest hadith number seen so far, for the plausibility filter
    all_results = {}
    match_types = {}

    for jpath in bab_files:
        with open(jpath, encoding="utf-8") as f:
            data = json.load(f)

        txt_path = os.path.join(book_dir, data.get("commentary_file", ""))
        if not os.path.exists(txt_path):
            print(f"  !! {os.path.basename(jpath)}: commentary_file not found ({txt_path}), skipping")
            continue

        with open(txt_path, encoding="utf-8") as f:
            body = f.read()

        verb_hits = extract_verb_matches(body)
        if verb_hits:
            hadith_numbers = verb_hits
            match_types[data["bab_number"]] = "verb match"
        else:
            plausible_min = max(1, running_max - 5)  # small tolerance for out-of-order babs
            fallback_hits = extract_fallback_matches(body, plausible_min)
            if fallback_hits:
                hadith_numbers = fallback_hits
                match_types[data["bab_number"]] = "fallback match (double-check)"
            else:
                hadith_numbers = []
                match_types[data["bab_number"]] = "STILL EMPTY"

        if hadith_numbers:
            running_max = max(running_max, max(hadith_numbers))

        all_results[data["bab_number"]] = hadith_numbers

        data["hadith_numbers"] = hadith_numbers
        with open(jpath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # per-bab report
    for bab_num in sorted(match_types):
        tag = match_types[bab_num]
        nums = all_results[bab_num]
        marker = "  " if tag == "verb match" else ("!!" if tag == "STILL EMPTY" else "? ")
        print(f"  {marker} bab {bab_num}: {tag} -> {nums}")

    # book-level summary
    all_nums = sorted(set(n for nums in all_results.values() for n in nums))
    if all_nums:
        internal_gaps = sorted(set(range(all_nums[0], all_nums[-1] + 1)) - set(all_nums))
        print(f"  Range: {all_nums[0]}-{all_nums[-1]} ({len(all_nums)} unique)")
        if internal_gaps:
            print(f"  !! Internal gaps: {internal_gaps}")
    counter = Counter(n for nums in all_results.values() for n in nums)
    dupes = {n: c for n, c in counter.items() if c > 1}
    if dupes:
        print(f"  !! Cross-bab duplicates: {dupes}")

    still_empty = [b for b, t in match_types.items() if t == "STILL EMPTY"]
    if still_empty:
        print(f"  !! {len(still_empty)} bab(s) still empty: {still_empty}")
        print(f"     If these genuinely have no hadith (title-only babs like bab 1 in "
              f"earlier books), that's fine. Otherwise paste the first ~300 characters "
              f"of one of these bab-*.txt files for a precise fix.")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    root_dir = sys.argv[1]
    book_dirs = sorted(
        d for d in glob.glob(os.path.join(root_dir, "book-*")) if os.path.isdir(d)
    )
    if not book_dirs:
        print(f"No book-* folders found under {root_dir}")
        sys.exit(1)

    for book_dir in book_dirs:
        process_book_folder(book_dir)

    print("\nDone. Check any '!!' lines above before trusting the results.")


if __name__ == "__main__":
    main()
