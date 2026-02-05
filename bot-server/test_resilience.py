import ast
import json
import re


# Test edecegimiz fonksiyonu buraya simule ediyoruz (main.py'dan kopyaladim)
def clean_and_repair_json(response_text):
    if not response_text:
        return "{}"

    # cleaning markdown code block
    clean_text = re.sub(r'```json\s*', '', response_text)
    clean_text = re.sub(r'```\s*', '', clean_text)

    # finding the actual braces
    start = clean_text.find('{')
    end = clean_text.rfind('}')
    if start != -1 and end != -1:
        clean_text = clean_text[start:end+1]

    # fixing the single-quote mess if it looks like a python dict
    if "'" in clean_text and '"' not in clean_text:
        try:
            data = ast.literal_eval(clean_text)
            return json.dumps(data)
        except (ValueError, SyntaxError):
            pass
    return clean_text

# --- TEST SENARYOLARI ---

scenarios = [
    {
        "name": "Scenario 1: Clean JSON",
        "input": '{"containers": {"chat": {"image": "chat:v2"}}}',
        "expected_valid": True
    },
    {
        "name": "Scenario 2: Markdown Block Wrapping",
        "input": 'Here is the output:\n```json\n{"namespace": "tournament", "replicas": 3}\n```',
        "expected_valid": True
    },
    {
        "name": "Scenario 3: Conversational Garbage (Pre/Post text)",
        "input": 'Sure, I updated the config.\n{"serviceEnv": "prod"}\nLet me know if you need anything else!',
        "expected_valid": True
    },
    {
        "name": "Scenario 4: Python Dict (Single Quotes) - The Killer",
        "input": "{'namespace': 'matchmaking', 'resources': {'cpu': '500m'}}",
        "expected_valid": True # Fonksiyon bunu duzeltip double quote yapmali
    },
    {
        "name": "Scenario 5: Broken/Incomplete JSON",
        "input": '{"namespace": "chat", "replicas": 3', # Kapanmayan parantez
        "expected_valid": False # Bu durumda patlamasi veya None donmesi lazim ama simdilik json.loads hata verecek
    }
]

print(f"{'TEST NAME':<50} | {'STATUS':<10} | {'RESULT'}")
print("-" * 80)

for case in scenarios:
    cleaned = clean_and_repair_json(case["input"])

    try:
        # JSON parse edilebiliyor mu?
        parsed = json.loads(cleaned)
        status = "PASS"

        # Ozel kontrol: Tek tirnaklar cift tirnaga dondu mu?
        if "'" in case["input"] and '"' not in case["input"]:
            if '"' in cleaned:
                msg = "Successfully converted single quotes"
            else:
                msg = "Failed to convert quotes"
                status = "FAIL"
        else:
            msg = json.dumps(parsed)[:20] + "..."

    except json.JSONDecodeError:
        if not case["expected_valid"]:
            status = "PASS (Expected Fail)"
            msg = "Invalid JSON caught correctly"
        else:
            status = "FAIL"
            msg = f"Could not parse: {cleaned}"

    print(f"{case['name']:<50} | {status:<10} | {msg}")
