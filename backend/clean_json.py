import json
import re
from pathlib import Path

# Resolve relative to this file (backend/) so the script is portable.
file_path = Path(__file__).resolve().parent / "parsed" / "08dbf8224013_claims.json"

with open(file_path, "r", encoding="utf-8") as f:
    claims = json.load(f)

def is_garbage(claim):
    source = claim.get("provenance", {}).get("source_sentence", "")
    numbers = re.findall(r'\b\d{1,3}(?:,\d{3})*(?:\.\d+)?\b', source)
    
    if len(numbers) > 6:
        return True
    
    tokens = source.split()
    if tokens and (len(numbers) / max(len(tokens), 1)) > 0.5:
        return True
        
    if not re.search(r"(increase|reduce|decrease|maintain|achieve|improve|drop|fall|rise)", source, re.IGNORECASE):
        return True
        
    return False

clean_claims = [c for c in claims if not is_garbage(c)]

print(f"Original claims: {len(claims)}")
print(f"Cleaned claims: {len(clean_claims)}")
print(f"Removed {len(claims) - len(clean_claims)} garbage claims.")

with open(file_path, "w", encoding="utf-8") as f:
    json.dump(clean_claims, f, indent=2)
