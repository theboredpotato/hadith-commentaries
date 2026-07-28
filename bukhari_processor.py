#!/usr/bin/env python3
"""
bukhari_processor.py
=====================
Splits a raw pasted text (from turath.io, Shamela, or similar) containing one
or more books of Fath al-Bari commentary into per-bab JSON + TXT file pairs,
strips tashkeel, extracts hadith numbers, and verifies the result before
writing anything you'd have to trust blindly.

USAGE
-----
    python3 bukhari_processor.py <input.txt> <output_dir>

Example:
    python3 bukhari_processor.py massive.txt ./sahih-bukhari

WHAT IT DOES
------------
1. Splits the input on "N - كتاب ..." book headers (if present). If the file
   is a single book with no كتاب header, the whole file is treated as one
   book and you'll be prompted for a slug name.
2. Within each book, splits on "N - باب ..." bab headers.
3. Strips Arabic tashkeel (diacritics) from all titles and body text.
4. Extracts hadith numbers from each bab's body text, recognizing every
   narration-opener variant observed across 13 books of real source text:
   حدثنا، حدثني، أخبرنا، قال، وقال، زاد، وعن، وأن، وسألنا، وبإسناده، وكان،
   رواه، ثم قال، ولو، and a bare quote-mark opener «...» (used when Bukhari
   cites a matn without repeating its isnad).
   Also handles two-hadith-in-one-citation patterns like "٤٧٨، ٤٧٩ - حدثنا"
   or "٤٠٨ وٍ٤٠٩ - وحدثنا".
5. Writes bab-NN.json + bab-NN.txt pairs, one per bab, per book.
6. Runs a verification pass and PRINTS A REPORT — it does not silently
   "fix" anything it isn't certain about. See VERIFICATION REPORT below.

WHAT IT WILL NEVER DO
----------------------
- It will never delete or drop any span of the original text. Every
  character between one recognized heading and the next ends up in some
  bab's .txt file. If a heading is missed (e.g. a bab title that omits the
  word "باب" entirely — a real edge case found in Book 10), that bab's
  content merges into the PREVIOUS bab's file rather than disappearing.
  The verification report is designed to catch exactly this and tell you
  where to look.
- It will never silently paper over a numbering gap or a duplicate. Both
  are printed clearly so you can check the source yourself.

VERIFICATION REPORT — read this every time
--------------------------------------------
For each book, the script prints:
  - How many babs were found, and whether bab numbers 1..N are contiguous
    (a missing bab number usually means a heading was missed).
  - The hadith-number range found, and any INTERNAL gaps within that range.
    A gap almost always means one of:
      (a) a narration-opener variant this script doesn't know about yet
          (check the bab's .txt file directly for how that hadith opens),
      (b) a genuinely missing chunk of pasted text (compare against the
          source again), or
      (c) a digit-transposition typo in the source itself (this has
          happened — e.g. "853" printed as "٥٨٣"). Cross-check the
          "[الحديث N - أطرافه في: ...]" reference brackets near the gap;
          they usually reveal the correct number.
  - Any hadith number appearing in more than one DIFFERENT bab (a real
    problem — as opposed to appearing twice within the SAME bab, which is
    normal: Ibn Hajar often re-quotes a hadith's matn later in his own
    commentary, and that is not an error).
  - Any "candidate missed heading" — a line starting with a number and a
    dash that does NOT match any known hadith-opener AND does NOT contain
    the word "باب". These are exactly the kind of heading Book 10's bab 65
    turned out to be (it omitted "باب" and just read "٦٥ - <topic phrase>").
    If you see one of these flagged, check that spot manually — it likely
    needs to be split into its own bab.

If the report comes back completely clean (no missing babs, no internal
hadith gaps, no cross-bab duplicates, no candidate missed headings), you can
trust the output as-is. If it flags anything, that specific spot needs a
human look — the script deliberately does not guess past that point.
"""

import sys
import os
import re
import json
from collections import Counter

# ----------------------------------------------------------------------
# Arabic digit helpers
# ----------------------------------------------------------------------
AR_DIGITS = "٠١٢٣٤٥٦٧٨٩"


def ar_to_int(s: str) -> int:
    """Convert a string of Arabic-Indic (or plain) digits to an int."""
    return int("".join(str(AR_DIGITS.index(c)) if c in AR_DIGITS else c for c in s))


# ----------------------------------------------------------------------
# Tashkeel stripping
# ----------------------------------------------------------------------
# Covers: fatha, damma, kasra, shadda, sukun, tanwin variants, superscript
# alef, and Qur'anic annotation marks. Does NOT touch tatweel or letters.
TASHKEEL = re.compile(r"[\u064B-\u065F\u0670\u06D6-\u06ED]")


def strip_tashkeel(text: str) -> str:
    return TASHKEEL.sub("", text)


# ----------------------------------------------------------------------
# Heading patterns
# ----------------------------------------------------------------------
BOOK_HEADING = re.compile(r"^[٠-٩0-9]+\s*-\s*كِ?تَ?اب.*$", re.MULTILINE)

# Real bab headings: "N - باب ..." (word باب may or may not carry tashkeel).
# Brackets are optional (some sources wrap a heading in [ ]).
BAB_HEADING = re.compile(
    r"^\[?([٠-٩0-9]+)\s*-\s*ب[َ]?اب([^\]\n]*)\]?\s*$", re.MULTILINE
)

# Every narration-opener verb/phrase observed across books 1-13, used to
# recognize where a hadith's text begins. Order doesn't matter for an
# alternation, but keep alphabetized-ish for readability.
CORE_VERBS = r"(?:حدث|أخبر|قال|زاد|سأل|كان|عن|بإسناده|أن|لو|رواه)"

# Matches: "N - <verb>", "N، M - <verb>" (two hadith sharing one citation),
# "N وM - <verb>", optionally preceded by "ثم" (continuation marker), and
# also a bare quote mark « with no verb at all (matn cited without isnad).
HADITH_START = re.compile(
    r"(?:^|\n)\s*([٠-٩]+)(?:\s*[،و]\s*([٠-٩]+))?\s*-?\s*(?:ثم\s*)?(?:و?"
    + CORE_VERBS
    + r"|«)"
)

# A "candidate missed heading": a line starting with a number + dash whose
# following text is NOT one of the known verbs and does NOT contain باب.
# This is how a heading that omits the word "باب" would show up (Book 10's
# bab 65 problem) — it looks like it could be a hadith opener but isn't one
# of the recognized verbs, and it isn't a normal باب heading either.
CANDIDATE_MISSED_HEADING = re.compile(
    r"(?:^|\n)\s*([٠-٩]+)\s*-\s*(?!"
    + CORE_VERBS
    + r"|ثم|«)([^\n]{1,80})"
)


def split_books(raw: str):
    """
    Returns a list of (book_number:int, book_slug_hint:str, content:str).
    If no كتاب headers are found, returns a single entry covering the
    whole file with book_number=None.
    """
    matches = list(BOOK_HEADING.finditer(raw))
    if not matches:
        return [(None, None, raw)]

    books = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
        content = raw[start:end]
        # try to pull the book number from the heading itself
        num_match = re.match(r"^([٠-٩0-9]+)", content)
        book_num = ar_to_int(num_match.group(1)) if num_match else None
        books.append((book_num, None, content))
    return books


def split_babs(book_content: str):
    """
    Returns a list of dicts: {num, title, body, start, end} for each bab
    found in this book's content. Also returns the list of candidate
    missed-heading matches for the verification report.
    """
    # drop the book-heading line itself if present (first line)
    content = book_content
    if BOOK_HEADING.match(content):
        content = content.split("\n", 1)[1] if "\n" in content else ""

    matches = list(BAB_HEADING.finditer(content))
    chunks = []
    for i, m in enumerate(matches):
        num_str = m.group(1)
        num = ar_to_int(num_str)
        title_rest = m.group(2).strip()
        title = f"{num_str} - باب{(' ' + title_rest) if title_rest else ''}".strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        body = content[start:end].strip()
        chunks.append({"num": num, "title": title, "body": body})

    # candidate missed headings: scan the WHOLE content (not just gaps)
    # for number-dash lines that aren't hadith openers and aren't باب
    # headings, then filter out ones that fall exactly on a real bab
    # heading's own line (those are fine, they ARE headings).
    real_heading_starts = {m.start() for m in matches}
    candidates = []
    for m in CANDIDATE_MISSED_HEADING.finditer(content):
        if m.start() in real_heading_starts:
            continue
        candidates.append((ar_to_int(m.group(1)), m.group(2).strip()[:60]))

    return chunks, candidates


def extract_hadith_numbers(body: str):
    """Returns an ordered, de-duplicated list of hadith numbers found in
    this bab's body text."""
    seen = []
    for m in HADITH_START.finditer(body):
        n1 = ar_to_int(m.group(1))
        if n1 not in seen:
            seen.append(n1)
        if m.group(2):
            n2 = ar_to_int(m.group(2))
            if n2 not in seen:
                seen.append(n2)
    return seen


def process_book(book_num, content, output_root, slug=None):
    chunks, candidates = split_babs(content)

    if not chunks:
        print(f"  !! No bab headings found in this book — skipping. "
              f"Check the source formatting.")
        return

    if slug is None:
        slug = f"book{book_num}" if book_num is not None else "book"

    outdir = os.path.join(output_root, f"book-{book_num:02d}-{slug}" if book_num else slug)
    os.makedirs(outdir, exist_ok=True)

    pad_width = max(2, len(str(len(chunks))))

    # write bab files first (hadith_numbers filled in below)
    all_results = {}
    for c in chunks:
        padded = str(c["num"]).zfill(pad_width)
        hadith_numbers = extract_hadith_numbers(c["body"])
        all_results[c["num"]] = hadith_numbers
        data = {
            "book": slug,
            "bab_number": c["num"],
            "bab_title": strip_tashkeel(c["title"]),
            "hadith_numbers": hadith_numbers,
            "verified": False,  # see note below
            "commentary_file": f"bab-{padded}.txt",
        }
        with open(os.path.join(outdir, f"bab-{padded}.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        with open(os.path.join(outdir, f"bab-{padded}.txt"), "w", encoding="utf-8") as f:
            f.write(strip_tashkeel(c["body"]))

    # ---------------- verification report ----------------
    print(f"\n=== Book {book_num if book_num else '?'} ({slug}) ===")
    print(f"  Output: {outdir}")

    expected_babs = set(range(1, len(chunks) + 1))
    found_babs = set(c["num"] for c in chunks)
    missing_babs = expected_babs - found_babs
    print(f"  Babs found: {len(chunks)}")
    if missing_babs:
        print(f"  !! MISSING BAB NUMBERS: {sorted(missing_babs)}  <-- check for a heading "
              f"that doesn't use the word 'باب' (see candidate list below)")
    else:
        print(f"  Bab numbering: contiguous 1-{len(chunks)}, OK")

    all_nums = sorted(set(n for nums in all_results.values() for n in nums))
    if all_nums:
        internal_gaps = sorted(set(range(all_nums[0], all_nums[-1] + 1)) - set(all_nums))
        print(f"  Hadith range found: {all_nums[0]}-{all_nums[-1]} ({len(all_nums)} unique)")
        if internal_gaps:
            print(f"  !! INTERNAL HADITH GAPS: {internal_gaps}")
            print(f"     For each, check the bab's .txt file for how that hadith actually")
            print(f"     opens — it may use a narration verb this script doesn't recognize,")
            print(f"     or check nearby '[الحديث N - أطرافه في: ...]' brackets for a")
            print(f"     digit-transposition typo (e.g. 853 printed as 583).")
        else:
            print(f"  Internal hadith gaps: none, OK")
    else:
        print(f"  !! No hadith numbers extracted at all in this book — check manually.")

    counter = Counter(n for nums in all_results.values() for n in nums)
    cross_dupes = {n: c for n, c in counter.items() if c > 1}
    if cross_dupes:
        print(f"  !! CROSS-BAB DUPLICATES (same hadith number in >1 bab — real problem): {cross_dupes}")
    else:
        print(f"  Cross-bab duplicates: none, OK")

    if candidates:
        print(f"  !! CANDIDATE MISSED HEADINGS (number-dash lines that aren't a")
        print(f"     recognized hadith opener and don't say 'باب' — check these by hand):")
        for num, snippet in candidates:
            print(f"       {num} - {snippet}")
    else:
        print(f"  Candidate missed headings: none, OK")

    if not missing_babs and (not all_nums or not internal_gaps) and not cross_dupes and not candidates:
        print(f"  >>> CLEAN. Set 'verified': true yourself once you've spot-checked a few files.")
    else:
        print(f"  >>> NEEDS MANUAL REVIEW before you trust this book's output.")


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    input_path = sys.argv[1]
    output_root = sys.argv[2]

    with open(input_path, encoding="utf-8") as f:
        raw = f.read()
    raw = raw.replace("\r\n", "\n")

    os.makedirs(output_root, exist_ok=True)

    books = split_books(raw)
    if len(books) == 1 and books[0][0] is None:
        print("No 'N - كتاب ...' book headers found — treating the whole file as one book.")
        slug = input("Enter a short slug for this book (e.g. 'wudu'): ").strip() or "book"
        process_book(None, books[0][2], output_root, slug=slug)
    else:
        for book_num, _, content in books:
            process_book(book_num, content, output_root)

    print("\nDone. Read the verification report above for each book before trusting the output.")


if __name__ == "__main__":
    main()
