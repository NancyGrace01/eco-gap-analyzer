import google.generativeai as genai
genai.configure(api_key="AIzaSyCJxDL576UinzRYXFSVyfnNk6kJOWan_D8")

try:
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            print(f"AVAILABLE MODEL: {m.name}")
except Exception as e:
    print(f"ERROR: {e}")