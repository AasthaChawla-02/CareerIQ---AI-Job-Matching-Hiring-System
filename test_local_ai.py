import subprocess

prompt = "Say hello in one short sentence."

result = subprocess.run(
    ["ollama", "run", "llama3", prompt],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    encoding="utf-8",
    errors="ignore"
)

print(result.stdout)
