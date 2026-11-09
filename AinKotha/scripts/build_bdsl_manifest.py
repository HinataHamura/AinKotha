"""Build frontend/bdsl/dataset.json (a flat ARRAY) from a folder of .sigml files.
Usage: python scripts/build_bdsl_manifest.py <sigml_root> [out.json]
english = text in parentheses in the file name, e.g. 'পানি (Water).sigml' -> 'Water',
else the SiGML gloss attribute, else the file stem."""
import json, re, sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).parent.parent / "frontend" / "bdsl" / "dataset.json"
bdsl_dir = out.parent.resolve()
entries = []
for f in sorted(root.rglob("*.sigml")):
    try:
        gloss = (re.search(r'gloss="([^"]*)"', f.read_text(encoding="utf-8", errors="ignore")) or [None, ""])[1]
    except OSError:
        continue
    m = re.search(r"\(([^)]+)\)", f.stem)
    english = (m.group(1) if m else gloss or f.stem).strip()
    try:
        rel = f.relative_to(bdsl_dir).as_posix()
    except ValueError:
        rel = f.relative_to(root).as_posix()  # files must then be copied under frontend/bdsl/
    entries.append({"gloss": gloss or f.stem, "english": english, "category": f.parent.name,
                    "sigmlPath": rel, "datasetRoot": ""})
out.write_text(json.dumps(entries, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"{len(entries)} entries -> {out}")
